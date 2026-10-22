import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.ai import client as ai_client, package as package_mod, prompts, runner, store as ai_store
from app.ai.client import ChatResult
from app.main import app
from app.memory import causes, context, patterns, similar, store as memory_store
from app.review import blocks

# Impressão digital da versão v2 dos prompts das lentes (v1 + regra de memória). Se falhar, alguém editou um texto publicado.
V2_FINGERPRINT = "a47ba1b6f18c"


def snap(trend=None, macd=None, prob=None, structure=None, sp=None, ai=None, **extra):
    s: dict = {}
    if trend or macd is not None:
        s["indicators"] = {"trend": trend, "macd_hist": macd}
    if prob:
        s["probability"] = {"label": prob}
    if structure:
        s["price_action"] = {"estrutura": structure}
    if sp:
        s["correlation"] = {"^GSPC": {"status": "estável", "corr_full": 0.7, "move20_other": sp, "other_unit": "%"}}
    if ai:
        s["ai"] = {"id": 1, "lenses": ai}
    s.update(extra)
    return s


_next = [0]


def row(status="alvo", direction="alta", market="acoes", symbol="AAA", setup="", decision="entrei", snapshot=None, created="2026-09-10T12:00:00+00:00", early=False, closed=True):
    _next[0] += 1
    return {
        "id": _next[0], "created_at": created, "closed_at": "2026-09-12T12:00:00+00:00" if closed and status != "aberta" else None,
        "market": market, "symbol": symbol, "decision": decision, "direction": direction, "status": status, "setup": setup,
        "snapshot_json": json.dumps(snapshot or {}), "early_exit_at": "2026-09-11T12:00:00+00:00" if early else None,
        "thesis": "SEGREDO-TESE", "entry_price": 123.456, "invalidation": 111.111, "target": 150.5, "r_multiple": 2.0,
    }


def many(n_hit, n_miss, **kw):
    return [row("alvo", **kw) for _ in range(n_hit)] + [row("invalidada", **kw) for _ in range(n_miss)]


# ---------- casos parecidos ----------

TARGET = {"market": "acoes", "symbol": "NVDA", "stances": {"tendencia": "alta", "macd": "alta", "probabilidade": "indistinta"}}


def test_score_adds_open_reasons_and_ignores_neutral_matches():
    same_asset = row(symbol="NVDA", snapshot=snap(trend="alta", macd=-1))
    pts, why = similar.score(TARGET, same_asset, similar.stances_of(same_asset))
    assert pts == 3 + 1 and why == ["mesmo ativo", "Tendência (médias): alta"]  # macd diverge: sem ponto
    same_market = row(symbol="AAPL", snapshot=snap(trend="alta", macd=0.5, prob="indistinta"))
    pts, why = similar.score(TARGET, same_market, similar.stances_of(same_market))
    assert pts == 1 + 1 + 1 and why == ["mesmo mercado", "Tendência (médias): alta", "MACD: alta"]  # "indistinta" nos dois não conta
    other_market = row(market="forex", symbol="EURUSD", snapshot=snap(trend="alta", macd=0.5))
    assert similar.score(TARGET, other_market, similar.stances_of(other_market))[0] == 2


def test_setups_and_direction_count_only_when_the_target_knows_them():
    r = row(symbol="AAPL", setup="Rompimento + Volume", direction="baixa")
    t = {**TARGET, "setups": ["Volume", "Outro"], "direction": "baixa"}
    pts, why = similar.score(t, r, similar.stances_of(r))
    assert pts == 1 + 2 + 1 and "setup em comum: Volume" in why and "mesma direção (baixa)" in why
    assert similar.score(TARGET, r, similar.stances_of(r))[0] == 1  # sem setups nem direção no alvo


def test_find_orders_by_points_then_recency_limits_k_and_skips_open_cases_and_self():
    best = row(symbol="NVDA", snapshot=snap(trend="alta", macd=1))
    older = row(symbol="AAPL", snapshot=snap(trend="alta", macd=1), created="2026-08-01T12:00:00+00:00")
    newer = row(symbol="MSFT", snapshot=snap(trend="alta", macd=1), created="2026-09-20T12:00:00+00:00")
    weak = row(symbol="AMD", snapshot=snap(trend="baixa"))
    still_open = row("aberta", symbol="NVDA", snapshot=snap(trend="alta", macd=1))
    me = row(symbol="NVDA", snapshot=snap(trend="alta", macd=1))
    out = similar.find(TARGET, [weak, older, newer, best, still_open, me], k=3, exclude_id=me["id"])
    assert [c["id"] for c in out["casos"]] == [best["id"], newer["id"], older["id"]]  # 5 pontos; depois 3, mais novo primeiro
    assert out["total_parecidos"] == 3 and out["criterio"] == {"minimo_de_pontos": 3, "maximo_de_casos": 3}
    assert out["casos"][0]["por_que_parecido"][0] == "mesmo ativo"
    assert similar.find(TARGET, [weak])["casos"] == []


def test_find_summarizes_every_match_by_direction_and_attaches_the_postmortem():
    a = row("alvo", symbol="AAPL", direction="alta", snapshot=snap(trend="alta", macd=1))
    b = row("invalidada", symbol="MSFT", direction="alta", snapshot=snap(trend="alta", macd=1))
    c = row("invalidada", symbol="AMD", direction="baixa", snapshot=snap(trend="alta", macd=1))
    pm = {"result": {"causa_principal": "evento_macro", "visibilidade": "so_ficou_claro_depois", "confianca": "baixa"}}
    out = similar.find(TARGET, [a, b, c], k=1, postmortems={b["id"]: pm, c["id"]: pm})
    g = out["grupo"]
    assert (g["todos"]["alvo"], g["todos"]["invalidada"]) == (1, 2)
    assert (g["teses_de_alta"]["alvo"], g["teses_de_alta"]["invalidada"], g["teses_de_baixa"]["invalidada"]) == (1, 1, 1)
    assert len(out["casos"]) == 1 and out["total_parecidos"] == 3  # o resumo usa todos, a lista só os k melhores
    shown = similar.find(TARGET, [b], postmortems={b["id"]: pm})["casos"][0]
    assert shown["pos_mortem"] == {"causa": "evento_macro", "visibilidade": "so_ficou_claro_depois", "confianca": "baixa"}


# ---------- alertas estatísticos ----------


def test_a_setup_that_clearly_differs_from_the_rest_raises_one_alert_with_the_case_counts():
    rows = many(4, 16, setup="A") + many(21, 9, setup="B")
    out = patterns.global_alerts(rows)
    setup_alerts = [a for a in out["alertas"] if a["tipo"] == "setup"]
    assert len(setup_alerts) == 1  # o espelho (B contra o resto) não vira um segundo alerta
    a = setup_alerts[0]
    assert a["chave"] == "A" and a["sentido"] == "pior" and a["n"] == 50
    assert (a["grupo"]["alvo"], a["grupo"]["fechadas"]) == (4, 20) and (a["contra"]["alvo"], a["contra"]["fechadas"]) == (21, 30)
    assert "4 de 20" in a["texto"] and "21 de 30" in a["texto"] and "n = 50" in a["texto"] and "−" in a["texto"]
    assert a["diferenca_pp"] == pytest.approx(-50.0) and a["ic95_pp"][1] < 0
    assert out["testadas"] >= 1 and out["esperados_por_acaso"] == round(0.05 * out["testadas"], 1)
    assert out["distinguiveis"] == len(out["alertas"]) and out["minimo_por_grupo"] == 10


def test_no_alert_without_enough_cases_or_without_a_real_difference():
    few = many(1, 8, setup="A") + many(25, 5, setup="B")  # A tem 9 resolvidas: abaixo do mínimo
    assert not [a for a in patterns.global_alerts(few)["alertas"] if a["tipo"] == "setup"]
    same = many(10, 10, setup="A") + many(10, 10, setup="B")
    out = patterns.global_alerts(same)
    assert out["alertas"] == [] and out["testadas"] >= 1 and out["distinguiveis"] == 0
    assert patterns.global_alerts([])["alertas"] == [] and patterns.global_alerts([])["testadas"] == 0


def test_decision_early_exit_market_and_block_alerts():
    entered = many(5, 15, decision="entrei", market="acoes", snapshot=snap(trend="alta"))
    skipped = many(18, 2, decision="nao_entrei", market="cripto", snapshot=snap(trend="baixa"))
    out = patterns.global_alerts(entered + skipped)
    kinds = {a["tipo"] for a in out["alertas"]}
    assert {"decisao", "mercado", "bloco"} <= kinds
    decision = next(a for a in out["alertas"] if a["tipo"] == "decisao")
    assert decision["sentido"] == "pior" and decision["grupo"]["rotulo"] == "entrou"
    block = next(a for a in out["alertas"] if a["tipo"] == "bloco" and a["chave"] == "tendencia")
    assert block["sentido"] == "pior" and block["n"] == 40  # a tendência "alta" concordou com as teses de alta que falharam

    early = many(2, 10, decision="entrei", early=True) + many(15, 3, decision="entrei", early=False)
    ealert = next(a for a in patterns.global_alerts(early)["alertas"] if a["tipo"] == "saida_antecipada")
    assert ealert["sentido"] == "pior" and ealert["grupo"]["rotulo"] == "saiu antes"


def test_cause_distribution_counts_the_ais_classification_with_intervals():
    def pm(cause, vis="visivel_na_epoca"):
        return {"result": {"causa_principal": cause, "visibilidade": vis}}

    pms = {i: pm("indicador_deu_ruido") for i in range(1, 4)}
    pms[4] = pm("evento_macro", "so_ficou_claro_depois")
    out = patterns.cause_distribution(pms)
    assert out["n"] == 4 and out["amostra"] == "insuficiente"
    assert [(i["causa"], i["n"]) for i in out["itens"]] == [("indicador_deu_ruido", 3), ("evento_macro", 1)]
    assert out["itens"][0]["taxa"] == 0.75 and out["itens"][0]["ic95"][0] < 0.75 < out["itens"][0]["ic95"][1]
    assert out["visibilidade"] == {"visivel_na_epoca": 3, "so_ficou_claro_depois": 1}
    assert "hipótese" in out["nota"]
    assert patterns.cause_distribution({}) == {**patterns.cause_distribution({}), "n": 0, "itens": []}


def test_asset_memory_keeps_only_the_alerts_that_apply_to_this_asset():
    rows = (
        many(4, 16, setup="A", market="acoes", snapshot=snap(trend="alta")) + many(21, 9, setup="B", market="acoes", snapshot=snap(trend="alta"))
        + many(2, 18, setup="C", market="cripto", decision="entrei") + many(25, 3, setup="D", market="forex", decision="nao_entrei")
    )
    state = {"tendencia": "alta", "macd": None}
    mem = patterns.asset_memory(rows, {}, "acoes", "AAA", state, ["A"])
    tipos = {(a["tipo"], a["chave"]) for a in mem["alertas_aplicaveis"]}
    assert ("setup", "A") in tipos and ("setup", "B") not in tipos  # só o setup que está em jogo
    assert ("mercado", "forex") not in tipos and ("mercado", "cripto") not in tipos
    assert not any(a["tipo"] == "bloco" and a["chave"] == "macd" for a in mem["alertas_aplicaveis"])
    assert mem["setups"][0]["setup"] == "A" and mem["setups"][0]["registros"] == 20
    assert mem["historico_do_ativo"]["registros"] == 50 and mem["comparacoes"]["minimo_por_grupo"] == 10
    assert mem["parecidos"]["total_parecidos"] > 0


# ---------- contexto para a análise com IA ----------


def fake_package(market="acoes", symbol="NVDA", horizon=10, slices=None):
    fatias = {
        "indicadores": {"valores": {"trend": "alta", "macd_hist": 0.4, "rsi14": 55, "close": 100, "sma20": 98, "atr14": 2}, "probabilidade": {"rotulo": "sem_dados"}},
        "price_action": {"estrutura": "topos e fundos ascendentes"},
        "macro": {"disponivel": True, "instrumentos": {"vix": {"ultimo": 16.0}}},
        "correlacao": {"disponivel": True, "referencias_fixas": {"sp500": {"status": "estável", "corr_full": 0.7, "move20_other": 2.0, "other_unit": "%"}}},
        "fundamentos": {"disponivel": True},
    }
    return {
        "ativo": {"mercado": market, "simbolo": symbol, "preco": 100.0, "horizonte_dias": horizon},
        "saude_dados": {"diario": {"fonte": "fake"}},
        "avisos": [],
        "fatias": {k: v for k, v in fatias.items() if slices is None or k in slices},
    }


def test_snapshot_from_package_gives_the_same_readings_the_diary_would_have():
    stances = blocks.derive(context.snapshot_from_package(fake_package()))
    assert stances == {
        "probabilidade": "sem_dados", "tendencia": "alta", "macd": "alta", "price_action": "alta", "corr_sp500": "alta", "corr_dxy": None,
    }
    assert blocks.derive(context.snapshot_from_package({"fatias": {}})) == {k: None for k, _, _ in blocks.BLOCKS}
    unavailable = {"fatias": {"correlacao": {"disponivel": False}}}
    assert context.snapshot_from_package(unavailable) == {}


LENSES = {"indicadores": {"inclinacao": "para_alta", "confianca": "media"}, "macro": {"inclinacao": "para_baixa", "confianca": "baixa"}}


def cases_for_memory():
    return [
        row("invalidada", symbol="NVDA", direction="alta", snapshot=snap(trend="alta", macd=1, structure="topos e fundos ascendentes", ai=LENSES)),
        row("alvo", symbol="AAPL", direction="alta", snapshot=snap(trend="alta", macd=1)),
        row("aberta", symbol="NVDA", snapshot=snap(trend="alta", macd=1)),
    ]


def test_memory_slice_states_when_there_is_nothing_to_remember():
    pkg = fake_package()
    assert context.build(pkg, [], {}) == {"disponivel": False, "motivo": "O diário ainda não tem casos resolvidos."}
    only_open = context.build(pkg, [row("aberta", snapshot=snap(trend="alta"))], {})
    assert only_open["disponivel"] is False
    dissimilar = context.build(pkg, [row("alvo", market="forex", symbol="EURUSD", snapshot=snap(trend="baixa"))], {})
    assert dissimilar["disponivel"] is True and dissimilar["casos"] == [] and "corte de semelhança" in dissimilar["avisos"][0]
    assert dissimilar["estado_atual_dos_blocos"]["tendencia"] == "alta"


def test_memory_slice_has_cases_statistics_and_a_small_sample_warning():
    entries = cases_for_memory()
    pm = {"result": {"causa_principal": "indicador_deu_ruido", "visibilidade": "visivel_na_epoca", "confianca": "media"}}
    mem = context.build(fake_package(), entries, {entries[0]["id"]: pm})
    assert mem["disponivel"] and len(mem["casos"]) == 2  # o caso aberto não entra
    first = mem["casos"][0]
    assert first["simbolo"] == "NVDA" and first["desfecho"] == "invalidada" and first["registrado_em"] == "2026-09"
    assert first["pos_mortem"]["causa"] == "indicador_deu_ruido" and first["dias_ate_desfecho"] == 2.0
    assert "mesmo ativo" in first["por_que_parecido"]
    stats = {s["descricao"]: s for s in mem["estatisticas"]}
    assert stats["teses de alta em casos parecidos"]["n"] == 2 and stats["teses de alta em casos parecidos"]["alvo"] == 1
    assert stats["teses neste mesmo ativo (qualquer estado)"]["n"] == 1
    assert any("Poucos casos parecidos (2)" in a for a in mem["avisos"])
    assert "hipótese" in mem["descricao"]


def test_memory_never_carries_free_text_decisions_or_prices():
    entries = cases_for_memory()
    mem = context.build(fake_package(), entries, {})
    for view in (mem, context.for_lens(mem, "indicadores")):
        dumped = json.dumps(view, ensure_ascii=False)
        assert "SEGREDO" not in dumped  # tese e notas
        for forbidden in ('"decisao"', '"decision"', '"thesis"', '"tese_do_operador"', '"entrada"', '"invalidacao"', '"alvo_em_R"', "123.456", "111.111", '"setup"', '"id"'):
            assert forbidden not in dumped, forbidden


def test_each_lens_sees_only_what_it_said_in_the_past():
    mem = context.build(fake_package(), cases_for_memory(), {})
    nvda_case = next(c for c in mem["casos"] if c["simbolo"] == "NVDA")
    assert nvda_case["_lentes"] == LENSES
    ind, macro, pa = (context.for_lens(mem, x) for x in ("indicadores", "macro", "price_action"))
    pick = lambda m: next(c for c in m["casos"] if c["simbolo"] == "NVDA")
    assert pick(ind)["sua_lente_dizia"] == LENSES["indicadores"] and pick(macro)["sua_lente_dizia"] == LENSES["macro"]
    assert pick(pa)["sua_lente_dizia"] is None  # essa lente não opinou naquele caso
    for view in (ind, macro, pa):
        assert all("_lentes" not in c for c in view["casos"])
    assert "_lentes" in nvda_case  # a fatia completa não foi alterada
    assert "casos" not in context.for_lens({"disponivel": False, "motivo": "x"}, "macro")


# ---------- prompt v2 e análise com memória ----------


def test_prompt_v2_is_frozen_and_v1_is_untouched():
    assert prompts.fingerprint("v2") == V2_FINGERPRINT and prompts.fingerprint("v1") == "a699a8d904ba"
    assert prompts.PROMPT_VERSION == "v1" and prompts.PROMPT_VERSIONS == ("v1", "v2")
    v1, v2 = prompts.system_prompt("acoes", "macro", "v1"), prompts.system_prompt("acoes", "macro", "v2")
    assert "dados.memoria" not in v1 and "dados.memoria" in v2
    assert prompts.BASE_V2.replace(prompts.MEMORY_RULE, "9. Seja direto") == prompts.BASE  # a v2 é a v1 + a regra, nada mais
    assert prompts.system_prompt("acoes", "macro") == v1  # padrão = v1
    with pytest.raises(KeyError):
        prompts.system_prompt("acoes", "macro", "v3")


class LensChat:
    def __init__(self):
        self.calls = []

    def __call__(self, system, user, schema):
        title = system.split("## Sua lente: ")[1].split("\n")[0]
        self.calls.append({"title": title, "system": system, "user": json.loads(user.split("\n", 1)[1])})
        out = {"inclinacao": "indistinta", "confianca": "media", "resumo": "Dados mistos.", "evidencias": [], "lacunas": [], "mudaria_a_conclusao": []}
        return ChatResult(data=out, text="{}", model="m", usage={"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01})


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "AI_MODEL", "m")
    db.init_db()


def seed_diary():
    for r in cases_for_memory():
        data = {k: r[k] for k in ("created_at", "market", "symbol", "decision", "direction", "status", "setup", "thesis", "entry_price", "invalidation", "target", "snapshot_json")}
        data.update(horizon_days=10, closed_at=r["closed_at"])
        db.insert_entry(data)


def test_analysis_with_memory_uses_v2_and_each_lens_gets_only_its_own_past(tmp_db):
    seed_diary()
    chat = LensChat()
    result = runner.analyze("acoes", "NVDA", 10, chat=chat, build=fake_package, memory=True)
    assert result["prompt_version"] == "v2" and result["prompt_fingerprint"] == V2_FINGERPRINT
    assert len(chat.calls) == 4
    for call in chat.calls:
        assert "dados.memoria" in call["system"]
        mem = call["user"]["dados"]["memoria"]
        assert mem["disponivel"] and mem["casos"]
        assert all("_lentes" not in c for c in mem["casos"])
        past = next(c for c in mem["casos"] if c["simbolo"] == "NVDA")["sua_lente_dizia"]
        expected = {"Indicadores": LENSES["indicadores"], "Macro": LENSES["macro"]}.get(call["title"])
        assert past == expected  # nunca o que outra lente disse
    saved = ai_store.get(result["id"])
    assert saved["prompt_version"] == "v2" and "memoria" in saved["package"]["fatias"]  # o pacote guardado é auditável


def test_analysis_without_memory_stays_on_v1_with_no_memory_anywhere(tmp_db):
    seed_diary()
    chat = LensChat()
    result = runner.analyze("acoes", "NVDA", 10, chat=chat, build=fake_package)
    assert result["prompt_version"] == "v1" and result["prompt_fingerprint"] == "a699a8d904ba"
    assert all("memoria" not in c["user"]["dados"] and "dados.memoria" not in c["system"] for c in chat.calls)
    assert "memoria" not in ai_store.get(result["id"])["package"]["fatias"]


@pytest.fixture
def api(tmp_db, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(package_mod, "build", fake_package)
    monkeypatch.setattr(ai_client, "chat_json", LensChat())
    with TestClient(app) as c:
        yield c


def test_api_memory_flag_prompt_versions_and_status(api):
    seed_diary()
    off = api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "NVDA"}).json()
    on = api.post("/api/ai/analyze", json={"market": "acoes", "symbol": "NVDA", "memory": True}).json()
    assert (off["prompt_version"], on["prompt_version"]) == ("v1", "v2")
    status = api.get("/api/ai/status").json()
    assert status["prompt_version"] == "v1" and status["memory_prompt_version"] == "v2" and status["memory_prompt_fingerprint"] == V2_FINGERPRINT
    v2 = api.get("/api/ai/prompts?version=v2").json()
    assert v2["version"] == "v2" and "dados.memoria" in v2["prompts"]["acoes"]["macro"]
    assert api.get("/api/ai/prompts").json()["version"] == "v1"
    assert api.get("/api/ai/prompts?version=v9").status_code == 404


def test_api_asset_memory_endpoint_reads_the_current_state_and_the_diary(api):
    seed_diary()
    body = api.get("/api/memory/asset/acoes/NVDA?horizon=10&setups=Rompimento").json()
    assert body["estado_atual"]["tendencia"] == "alta" and body["estado_atual"]["price_action"] == "alta"
    assert body["parecidos"]["total_parecidos"] == 2 and body["parecidos"]["casos"][0]["simbolo"] == "NVDA"
    assert body["historico_do_ativo"]["registros"] == 2  # as duas teses de NVDA (uma aberta)
    assert body["setups"][0]["setup"] == "Rompimento" and "comparacoes" in body
    assert api.get("/api/memory/asset/acoes/").status_code in (404, 405)
    assert api.get("/api/memory/asset/bolsa/NVDA").status_code == 422


def test_the_fixed_cause_list_can_be_read_by_the_ui(api):
    lista = api.get("/api/memory").json()["causas"]["lista"]
    assert [c["id"] for c in lista] == list(causes.CAUSE_IDS)
    assert all(c["title"] and c["definition"] for c in lista)
