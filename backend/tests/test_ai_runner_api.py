import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.ai import client, package as package_mod, prompts, runner, store
from app.ai.client import AIError, ChatResult
from app.main import app
from app.providers.base import ProviderError


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "AI_MODEL", "anthropic/claude-sonnet-5.5")
    monkeypatch.setattr(config, "AI_REASONING_EFFORT", "low")
    db.init_db()


def fake_package(market, symbol, horizon, slices):
    fatias = {
        "indicadores": {"valores": {"rsi14": 47.9, "trend": "lateral"}, "probabilidade": {"rotulo": "indistinta", "p_alta": 0.62}},
        "price_action": {"estrutura": "topos e fundos ascendentes", "suporte_proximo": {"preco": 208.9, "dist_atr": 0.56}},
        "macro": {"disponivel": True, "instrumentos": {"vix": {"ultimo": 16.7, "var_20d": 9.66}}},
        "correlacao": {"disponivel": True, "referencias_fixas": {"sp500": {"status": "estável", "corr_full": 0.7}}},
        "fundamentos": {"disponivel": True, "pl_12m": 26.9},
        "par": {"tipo": "par de moedas", "base": "EUR", "cotacao": "USD"},
    }
    return {
        "ativo": {"mercado": market, "simbolo": symbol.upper(), "preco": 212.4, "horizonte_dias": horizon},
        "saude_dados": {"diario": {"fonte": "fake"}},
        "avisos": [],
        "fatias": {k: v for k, v in fatias.items() if k in slices},
    }


def good_output(**kw):
    out = {
        "inclinacao": "indistinta",
        "confianca": "media",
        "resumo": "Dados mistos.",
        "evidencias": [
            {"campo": "dados.indicadores.valores.rsi14", "valor": "47,9", "leitura": "neutro", "aponta_para": "neutro"},
        ],
        "lacunas": ["calendário econômico"],
        "mudaria_a_conclusao": ["RSI acima de 65"],
    }
    return {**out, **kw}


class FakeChat:
    """Substitui a OpenRouter: guarda cada chamada e devolve uma saída por lente."""

    def __init__(self, outputs=None, fail=None, cost=0.01):
        self.calls, self.outputs, self.fail, self.cost = [], outputs or {}, fail or {}, cost

    def __call__(self, system, user, schema):
        lens_title = system.split("## Sua lente: ")[1].split("\n")[0]
        self.calls.append({"system": system, "user": user, "schema": schema, "lens": lens_title})
        if lens_title in self.fail:
            raise self.fail[lens_title]
        return ChatResult(
            data=self.outputs.get(lens_title, good_output()), text="{}", model="anthropic/claude-sonnet-5.5",
            usage={"prompt_tokens": 1000, "completion_tokens": 400, "cost": self.cost},
        )


# ---------- validação da saída ----------


def test_validate_output_normalizes_and_is_lenient_on_the_small_things():
    out = runner.validate_output(good_output(
        evidencias=[{"campo": " dados.x ", "valor": 12, "leitura": "l", "aponta_para": "nada"}, "lixo", {"campo": ""}],
        lacunas=["a", "", 3],
        mudaria_a_conclusao="nao é lista",
    ))
    assert out["evidencias"] == [{"campo": "dados.x", "valor": "12", "leitura": "l", "aponta_para": "neutro"}]
    assert out["lacunas"] == ["a", "3"] and out["mudaria_a_conclusao"] == []


@pytest.mark.parametrize(
    "patch",
    [{"inclinacao": "comprar"}, {"inclinacao": None}, {"confianca": "altíssima"}, {"resumo": "  "}],
)
def test_validate_output_is_strict_on_stance_confidence_and_summary(patch):
    with pytest.raises(runner.OutputError):
        runner.validate_output(good_output(**patch))


# ---------- isolamento e execução de cada lente ----------


def test_each_lens_receives_only_its_own_slices_plus_the_common_part():
    pkg = fake_package("acoes", "NVDA", 10, {"indicadores", "price_action", "macro", "correlacao", "fundamentos"})
    per = runner.lens_packages(pkg, prompts.MARKET_LENSES["acoes"])
    assert set(per["indicadores"]["dados"]) == {"indicadores"}
    assert set(per["price_action"]["dados"]) == {"price_action"}
    assert set(per["macro"]["dados"]) == {"macro", "correlacao"}
    assert set(per["fundamentalista"]["dados"]) == {"fundamentos"}
    for p in per.values():
        assert {"ativo", "saude_dados", "avisos"} <= set(p)


def test_run_lens_counts_citations_that_check_out_and_the_invented_ones():
    pkg = runner.lens_packages(fake_package("acoes", "NVDA", 10, {"indicadores"}), ["indicadores"])["indicadores"]
    out = good_output(evidencias=[
        {"campo": "dados.indicadores.valores.rsi14", "valor": "47,9", "leitura": "ok", "aponta_para": "neutro"},
        {"campo": "dados.indicadores.valores.rsi14", "valor": "70", "leitura": "valor errado", "aponta_para": "baixa"},
        {"campo": "dados.indicadores.valores.inventado", "valor": "1", "leitura": "campo falso", "aponta_para": "alta"},
    ])
    r = runner.run_lens("acoes", prompts.LENSES["indicadores"], pkg, FakeChat({"Indicadores": out}))
    assert r["status"] == "ok" and r["citacoes"] == {"total": 3, "conferem": 1, "nao_conferem": 2}
    assert [e["verificada"] for e in r["resultado"]["evidencias"]] == [True, False, False]
    assert r["uso"]["cost"] == 0.01 and r["duracao_ms"] >= 0


def test_run_lens_turns_failures_into_a_lens_error_instead_of_raising():
    pkg = runner.lens_packages(fake_package("acoes", "NVDA", 10, {"indicadores"}), ["indicadores"])["indicadores"]
    lens = prompts.LENSES["indicadores"]
    r = runner.run_lens("acoes", lens, pkg, FakeChat(fail={"Indicadores": AIError("limite", "devagar")}))
    assert r["status"] == "erro" and r["erro"] == {"tipo": "limite", "mensagem": "devagar"}
    r = runner.run_lens("acoes", lens, pkg, FakeChat({"Indicadores": good_output(inclinacao="vender")}))
    assert r["status"] == "erro" and r["erro"]["tipo"] == "resposta_invalida"


# ---------- análise completa ----------


@pytest.mark.parametrize("market,n_lenses", [("acoes", 4), ("forex", 3), ("cripto", 3)])
def test_analyze_runs_one_call_per_lens_with_the_right_prompt_and_saves(market, n_lenses):
    chat = FakeChat()
    res = runner.analyze(market, "ativo", 10, chat=chat, build=fake_package)
    assert len(chat.calls) == n_lenses and [r["lente"] for r in res["lenses"]] == prompts.MARKET_LENSES[market]
    for call, lens_id in zip(sorted(chat.calls, key=lambda c: c["lens"]), sorted(prompts.MARKET_LENSES[market], key=lambda i: prompts.LENSES[i].title)):
        assert call["system"] == prompts.system_prompt(market, lens_id) and call["schema"] is prompts.LENS_SCHEMA
        assert json.loads(call["user"].split("\n", 1)[1])["ativo"]["mercado"] == market
    assert res["prompt_version"] == "v1" and res["prompt_fingerprint"] == prompts.fingerprint()
    assert res["cost_usd"] == pytest.approx(0.01 * n_lenses) and res["prompt_tokens"] == 1000 * n_lenses
    saved = store.get(res["id"])
    assert saved["symbol"] == "ATIVO" and saved["model"] == "anthropic/claude-sonnet-5.5" and saved["effort"] == "low"
    assert saved["package"]["ativo"]["simbolo"] == "ATIVO" and [l["lente"] for l in saved["lenses"]] == prompts.MARKET_LENSES[market]


def test_each_lens_call_does_not_see_the_other_lens_data():
    chat = FakeChat()
    runner.analyze("acoes", "NVDA", 10, chat=chat, build=fake_package)
    by_lens = {c["lens"]: json.loads(c["user"].split("\n", 1)[1])["dados"] for c in chat.calls}
    assert set(by_lens["Indicadores"]) == {"indicadores"} and set(by_lens["Price action"]) == {"price_action"}
    assert "price_action" not in json.dumps(by_lens["Indicadores"]) and "rsi14" not in json.dumps(by_lens["Price action"])


def test_one_failing_lens_does_not_sink_the_analysis():
    res = runner.analyze("acoes", "NVDA", 10, chat=FakeChat(fail={"Macro": AIError("servidor", "fora do ar")}), build=fake_package)
    status = {r["lente"]: r["status"] for r in res["lenses"]}
    assert status == {"macro": "erro", "fundamentalista": "ok", "indicadores": "ok", "price_action": "ok"}
    assert res["cost_usd"] == pytest.approx(0.03)
    assert store.get(res["id"])["lenses"][0]["erro"]["tipo"] == "servidor"


def test_all_lenses_failing_raises_and_saves_nothing():
    with pytest.raises(AIError) as exc:
        runner.analyze("forex", "EURUSD", 10, chat=FakeChat(fail={t: AIError("creditos", "sem saldo") for t in ("Macro e fundamentos", "Indicadores", "Price action")}), build=fake_package)
    assert exc.value.kind == "creditos"
    assert store.list_for_asset("forex", "EURUSD") == []


def test_missing_key_fails_before_building_the_package(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    built = []
    with pytest.raises(AIError) as exc:
        runner.analyze("acoes", "NVDA", 10, build=lambda *a: built.append(1))
    assert exc.value.kind == "sem_chave" and built == []


def test_cost_is_none_when_the_provider_does_not_report_it():
    res = runner.analyze("cripto", "BTCUSDT", 10, chat=FakeChat(cost=None), build=fake_package)
    assert res["cost_usd"] is None


def test_store_lists_per_asset_and_averages_cost():
    for cost in (0.02, 0.04):
        runner.analyze("acoes", "NVDA", 10, chat=FakeChat(cost=cost / 4), build=fake_package)
    runner.analyze("acoes", "AAPL", 10, chat=FakeChat(cost=0.01), build=fake_package)
    assert [a["symbol"] for a in store.list_for_asset("acoes", "NVDA")] == ["NVDA", "NVDA"]
    assert "package" not in store.list_for_asset("acoes", "NVDA")[0]
    assert store.recent_avg_cost() == pytest.approx((0.02 + 0.04 + 0.04) / 3)


# ---------- rotas ----------


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(package_mod, "build", fake_package)
    with TestClient(app) as c:
        yield c


def test_status_and_prompts_endpoints(api, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    st = api.get("/api/ai/status").json()
    assert st["configured"] is False and st["model"] == "anthropic/claude-sonnet-5.5" and st["prompt_version"] == "v1"
    assert [l["id"] for l in st["lenses"]["cripto"]] == ["referencia", "indicadores", "price_action"] and st["avg_cost_usd"] is None
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-x")
    assert api.get("/api/ai/status").json()["configured"] is True
    shown = api.get("/api/ai/prompts").json()
    assert shown["fingerprint"] == prompts.fingerprint() and "Sua lente: Macro" in shown["prompts"]["acoes"]["macro"]
    assert "OPENROUTER_API_KEY" not in json.dumps(shown) and "sk-or-x" not in json.dumps(st)


def test_analyze_endpoint_success_and_listing(api, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-x")
    monkeypatch.setattr(client, "chat_json", FakeChat())
    r = api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "nvda", "horizon": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "NVDA" and body["horizon_days"] == 5 and len(body["lenses"]) == 4 and "package" not in body
    assert body["lenses"][0]["resultado"]["inclinacao"] == "indistinta"
    assert "veredito" not in json.dumps(body).lower()

    listed = api.get("/api/ai/analyses", params={"market": "acoes", "symbol": "NVDA"}).json()
    assert [a["id"] for a in listed] == [body["id"]]
    detail = api.get(f"/api/ai/analyses/{body['id']}").json()
    assert detail["package"]["ativo"]["simbolo"] == "NVDA"
    assert api.get("/api/ai/analyses/999").status_code == 404


@pytest.mark.parametrize(
    "kind,status", [("sem_chave", 400), ("auth", 401), ("creditos", 402), ("limite", 429), ("servidor", 502), ("pedido", 502)]
)
def test_analyze_endpoint_maps_errors_to_http_status(api, monkeypatch, kind, status):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-x")

    def boom(system, user, schema):
        raise AIError(kind, f"erro {kind}")

    monkeypatch.setattr(client, "chat_json", boom)
    r = api.post("/api/ai/analyze", json={"market": "forex", "symbol": "EURUSD"})
    assert r.status_code == status and r.json()["detail"] == f"erro {kind}"


def test_analyze_endpoint_without_key_never_touches_the_network(api, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    called = []
    monkeypatch.setattr(package_mod, "build", lambda *a: called.append(1))
    r = api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "NVDA"})
    assert r.status_code == 400 and ".env" in r.json()["detail"] and called == []


def test_analyze_endpoint_validation_and_missing_prices(api, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-x")
    assert api.post("/api/ai/analyze", json={"market": "forex", "symbol": "EUR"}).status_code == 422
    assert api.post("/api/ai/analyze", json={"market": "bolsa", "symbol": "X"}).status_code == 422
    assert api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "NVDA", "horizon": 500}).status_code == 422

    def no_prices(*a):
        raise ProviderError("Yahoo sem dados")

    monkeypatch.setattr(package_mod, "build", no_prices)
    r = api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "NVDA"})
    assert r.status_code == 502 and "Yahoo sem dados" in r.json()["detail"]
