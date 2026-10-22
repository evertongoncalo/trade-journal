import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.ai import client as ai_client, store as ai_store
from app.ai.client import AIError, ChatResult
from app.main import app
from app.memory import causes, postmortem, store
from app.providers.base import ProviderError

# Impressão digital do pós-mortem pm-v1 (prompt + esquema + lista de causas). Se este teste falhar, alguém editou um texto
# publicado: NÃO atualize o valor; crie PM_VERSION = "pm-v2" (e causas-v2, se a lista mudar) e fixe o hash novo.
PM_V1_FINGERPRINT = "f6d918ee36b2"

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
CREATED = "2026-10-01T12:00:00+00:00"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "AI_MODEL", "anthropic/claude-sonnet-5.5")
    monkeypatch.setattr(config, "AI_REASONING_EFFORT", "low")
    db.init_db()


def snapshot(**kw):
    snap = {
        "price": 100.0,
        "indicators": {"close": 100.0, "sma20": 98.0, "atr14": 2.0, "rsi14": 61.0, "trend": "alta", "macd_hist": 0.3},
        "probability": {"label": "indistinta", "n": 40},
        "price_action": {"estrutura": "topos e fundos ascendentes", "variacao_pct": {"5d": 2.0, "20d": 6.0}},
        "correlation": {"^GSPC": {"label": "S&P 500", "status": "estável", "corr_full": 0.7, "move20_other": 2.0, "other_unit": "%"}},
    }
    snap.update(kw)
    return snap


def add_entry(**kw):
    data = dict(
        created_at=CREATED, market="acoes", symbol="NVDA", decision="entrei", direction="alta", entry_price=100.0,
        invalidation=95.0, target=110.0, horizon_days=10, thesis="rompimento com volume", setup="Rompimento",
        snapshot_json=json.dumps(snapshot()), status="invalidada", closed_at="2026-10-01T15:00:00+00:00",
        exit_price=95.0, r_multiple=-1.0,
    )
    data.update(kw)
    return db.insert_entry(data)


def hourly():
    idx = pd.date_range("2026-10-01 12:00", periods=5, freq="h", tz="UTC")
    rows = [(100, 101, 99.5, 100.5), (100.5, 103, 100, 102), (102, 104, 98, 99), (99, 99.5, 94.5, 95), (95, 112, 95, 111)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx).assign(Volume=1.0)


def fake_bars(entry, now):
    return hourly(), "1h"


def closes():
    idx = pd.date_range("2026-09-25", "2026-10-10", freq="D")
    frame = pd.DataFrame({"^GSPC": 5000.0, "DX-Y.NYB": 100.0, "^VIX": 15.0}, index=idx)
    frame.loc[frame.index > pd.Timestamp("2026-10-01"), "^GSPC"] = 4800.0  # -4%: referência notável
    return frame


def good(**kw):
    out = {
        "causa_principal": "indicador_deu_ruido", "causas_secundarias": [], "visibilidade": "visivel_na_epoca",
        "confianca": "media", "resumo": "Os sinais eram mistos no registro.",
        "o_que_era_visivel": ["probabilidade indistinta"], "o_que_so_ficou_claro_depois": [],
        "evidencias": [{"campo": "depois.caminho_do_preco.excursao_contra_max_R", "valor": "-1,1", "leitura": "foi contra"}],
        "hipoteses": [], "o_que_faltou": ["calendário econômico"],
    }
    return {**out, **kw}


class FakeChat:
    def __init__(self, output=None, cost=0.03, error=None):
        self.calls, self.output, self.cost, self.error = [], output if output is not None else good(), cost, error

    def __call__(self, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self.error:
            raise self.error
        return ChatResult(data=self.output, text="{}", model="x", usage={"prompt_tokens": 2000, "completion_tokens": 600, "cost": self.cost})


def run(entry_id, chat=None, **kw):
    return postmortem.run(
        entry_id, chat=chat or FakeChat(), fetch_bars=kw.pop("fetch_bars", fake_bars),
        load_closes=kw.pop("load_closes", closes), now=NOW, **kw,
    )


# ---------- prompt, esquema e causas ----------


def test_published_postmortem_prompt_is_frozen():
    assert postmortem.PM_VERSION == "pm-v1" and causes.CAUSES_VERSION == "causas-v1"
    assert postmortem.fingerprint() == PM_V1_FINGERPRINT


def test_the_cause_list_is_the_one_in_the_spec_and_the_schema_uses_it():
    assert causes.CAUSE_IDS == (
        "evento_macro", "referencia_divergiu", "indicador_deu_ruido", "invalidacao_ignorada", "entrada_tardia",
        "sem_causa_identificavel",
    )
    assert postmortem.PM_SCHEMA["properties"]["causa_principal"]["enum"] == list(causes.CAUSE_IDS)
    assert postmortem.PM_SCHEMA["additionalProperties"] is False
    assert set(postmortem.PM_SCHEMA["required"]) == set(postmortem.PM_SCHEMA["properties"])  # modo estrito: tudo obrigatório
    assert {c.id for c in causes.CAUSES if c.only_if_entered} == {"invalidacao_ignorada", "entrada_tardia"}


def test_prompt_lists_every_cause_and_warns_about_hindsight_and_missing_calendar():
    text = postmortem.system_prompt()
    assert all(f"- {cid}:" in text for cid in causes.CAUSE_IDS)
    assert "viés retrospectivo" in text.lower() and "sem_causa_identificavel" in text
    assert "calendário econômico" in text and "hipóteses" in text and "versão causas-v1" in text


# ---------- elegibilidade ----------


def row(**kw):
    return {"status": "alvo", "early_exit_at": None, **kw}


def test_triggers_are_an_invalidated_thesis_and_or_an_early_exit():
    assert postmortem.trigger_label(row()) is None
    assert postmortem.trigger_label(row(status="expirada")) is None
    assert postmortem.trigger_label(row(status="aberta")) is None
    assert postmortem.trigger_label(row(status="invalidada")) == "invalidada"
    assert postmortem.trigger_label(row(early_exit_at="x")) == "saida_antecipada"
    assert postmortem.trigger_label(row(status="invalidada", early_exit_at="x")) == "ambos"


# ---------- pacote ----------


def test_package_separates_what_was_visible_from_what_came_after():
    eid = add_entry(early_exit_at="2026-10-01T14:00:00+00:00", early_exit_price=99.0, early_exit_r=-0.2, early_exit_reason="medo")
    entry = db.get_entry(eid)
    snap = json.loads(entry["snapshot_json"])
    pkg = postmortem.build_package(entry, snap, {"disponivel": True, "saida_antecipada": {"invalidacao_tocada_antes": False}}, {"notaveis": ["sp500"]})
    assert set(pkg) == {"caso", "gatilhos", "visivel_na_epoca", "depois", "lacunas_conhecidas"}
    assert pkg["gatilhos"] == ["tese_invalidada", "saida_antecipada"]
    caso = pkg["caso"]
    assert caso["plano"] == {"entrada": 100.0, "invalidacao": 95.0, "alvo": 110.0, "risco_pct": 5.0, "alvo_em_R": 2.0}
    assert caso["tese_do_operador"] == "rompimento com volume"  # o pós-mortem envia a tese: é dito na tela e no README
    assert caso["saida_antecipada"]["motivo_do_operador"] == "medo"
    vis = pkg["visivel_na_epoca"]
    assert vis["blocos_de_codigo"]["tendencia"] == {"inclinacao": "alta", "em_relacao_a_tese": "concorda"}
    assert vis["blocos_de_codigo"]["probabilidade"]["em_relacao_a_tese"] == "sem_lado"
    assert "depois" not in vis and "caminho_do_preco" not in vis  # nada do futuro no bloco "na época"
    assert pkg["depois"]["referencias_notaveis"] == ["sp500"]
    assert "calendário econômico" in " ".join(pkg["lacunas_conhecidas"])


def test_stretched_is_signed_by_the_direction_of_the_thesis():
    snap = snapshot()
    up = postmortem.stretched(snap, "alta")
    assert up["variacao_5d_a_favor_pct"] == 2.0 and up["variacao_20d_a_favor_pct"] == 6.0
    assert up["distancia_da_mm20_em_atr_a_favor"] == 1.0  # (100 - 98) / 2
    down = postmortem.stretched(snap, "baixa")
    assert down["variacao_5d_a_favor_pct"] == -2.0 and down["distancia_da_mm20_em_atr_a_favor"] == -1.0
    assert postmortem.stretched({}, "alta")["variacao_5d_a_favor_pct"] is None  # registro antigo: sem inventar


def test_ai_lens_summaries_come_from_the_stored_analysis():
    analysis = {
        "created_at": "2026-10-01T11:00:00+00:00", "market": "acoes", "symbol": "NVDA", "horizon_days": 10,
        "prompt_version": "v1", "prompt_fingerprint": "x", "model": "m", "effort": None, "cost_usd": None,
        "prompt_tokens": 0, "completion_tokens": 0, "duration_ms": 1,
        "lenses": [
            {"lente": "macro", "status": "ok", "resultado": {"inclinacao": "para_baixa", "confianca": "baixa", "resumo": "VIX subindo", "lacunas": ["a", "b", "c", "d"]}},
            {"lente": "indicadores", "status": "erro", "erro": {}},
        ],
    }
    ai_id = ai_store.save(analysis, {})
    eid = add_entry(snapshot_json=json.dumps(snapshot(ai={"id": ai_id, "lenses": {}})))
    entry = db.get_entry(eid)
    pkg = postmortem.build_package(entry, json.loads(entry["snapshot_json"]), {"disponivel": True}, {})
    assert pkg["visivel_na_epoca"]["lentes_de_ia"] == {
        "macro": {"inclinacao": "para_baixa", "confianca": "baixa", "resumo": "VIX subindo", "lacunas": ["a", "b", "c"]}
    }
    gone = postmortem.build_package(entry, snapshot(ai={"id": 999}), {"disponivel": True}, {})
    assert gone["visivel_na_epoca"]["lentes_de_ia"] is None


# ---------- validação e verificações ----------


def test_validate_output_is_strict_on_the_fixed_list():
    out = postmortem.validate_output(good(causas_secundarias=["entrada_tardia", "entrada_tardia", "indicador_deu_ruido", "sem_causa_identificavel", "inventada"], hipoteses=["a", "b", "c"]))
    assert out["causas_secundarias"] == ["entrada_tardia"]  # sem repetir, sem a principal, sem "sem causa", sem inventada
    assert out["hipoteses"] == ["a", "b"]
    for bad in (good(causa_principal="azar"), good(visibilidade="talvez"), good(confianca="muita"), good(resumo="  ")):
        with pytest.raises(postmortem.OutputError):
            postmortem.validate_output(bad)


def checks_for(output, decision="entrei", **pkg):
    entry = {"decision": decision}
    depois = {"caminho_do_preco": pkg.get("path", {"saida_antecipada": None}), "referencias_notaveis": pkg.get("notaveis", [])}
    package = {"depois": depois, "visivel_na_epoca": {"esticado": pkg.get("esticado", {})}}
    result = postmortem.validate_output(good(**output))
    result["evidencias"] = [{**e, "verificada": e.get("verificada")} for e in result["evidencias"]]
    return {c["tipo"] for c in postmortem.run_checks(result, package, entry)}, postmortem.run_checks(result, package, entry)


def test_checks_flag_causes_that_do_not_apply_or_have_no_basis():
    kinds, _ = checks_for({"causa_principal": "entrada_tardia"}, decision="nao_entrei", esticado={"variacao_5d_a_favor_pct": 3.0})
    assert kinds == {"nao_se_aplica"}
    kinds, _ = checks_for({"causa_principal": "invalidacao_ignorada"}, path={"saida_antecipada": None})
    assert "sem_base" in kinds
    kinds, _ = checks_for({"causa_principal": "invalidacao_ignorada"}, path={"saida_antecipada": {"invalidacao_tocada_antes": True}})
    assert "sem_base" not in kinds
    kinds, _ = checks_for({"causa_principal": "evento_macro"}, notaveis=[])
    assert "sem_base" in kinds
    kinds, _ = checks_for({"causa_principal": "evento_macro"}, notaveis=["sp500"])
    assert "sem_base" not in kinds
    kinds, _ = checks_for({"causa_principal": "entrada_tardia"}, esticado={"variacao_5d_a_favor_pct": -1.0, "variacao_20d_a_favor_pct": -3.0})
    assert "sem_base" in kinds
    kinds, _ = checks_for({"causa_principal": "entrada_tardia"}, esticado={"variacao_5d_a_favor_pct": 4.0, "variacao_20d_a_favor_pct": 9.0})
    assert "sem_base" not in kinds


def test_checks_flag_incoherent_answers_and_unverified_citations():
    kinds, _ = checks_for({"causa_principal": "sem_causa_identificavel", "causas_secundarias": ["entrada_tardia"], "visibilidade": "nao_se_aplica"}, esticado={"variacao_5d_a_favor_pct": 3.0})
    assert "incoerente" in kinds
    kinds, _ = checks_for({"visibilidade": "visivel_na_epoca", "o_que_so_ficou_claro_depois": ["x"]})
    assert "incoerente" in kinds
    kinds, _ = checks_for({"visibilidade": "so_ficou_claro_depois", "o_que_era_visivel": ["y"]})
    assert "incoerente" in kinds
    out = postmortem.validate_output(good(evidencias=[{"campo": "a", "valor": "1", "leitura": ""}, {"campo": "b", "valor": "2", "leitura": ""}]))
    out["evidencias"][0]["verificada"], out["evidencias"][1]["verificada"] = False, True
    found = postmortem.run_checks(out, {"depois": {"caminho_do_preco": {}, "referencias_notaveis": []}, "visivel_na_epoca": {"esticado": {}}}, {"decision": "entrei"})
    assert [c["tipo"] for c in found] == ["citacao"] and "1 de 2" in found[0]["mensagem"]
    assert checks_for({})[0] == set()  # resposta limpa: nenhum aviso


# ---------- execução ----------


def test_run_end_to_end_stores_the_result_the_package_and_the_cost():
    eid = add_entry()
    chat = FakeChat()
    pm = run(eid, chat)
    assert pm["id"] and pm["trigger"] == "invalidada" and pm["prompt_version"] == "pm-v1"
    assert pm["prompt_fingerprint"] == PM_V1_FINGERPRINT and pm["causes_version"] == "causas-v1"
    assert pm["cost_usd"] == 0.03 and pm["prompt_tokens"] == 2000 and pm["checks"] == []
    assert pm["result"]["causa_principal"] == "indicador_deu_ruido"
    assert pm["result"]["evidencias"][0]["verificada"] is True  # -1,1 bate com o pacote (excursão contra de -1,1 R)

    (call,) = chat.calls
    assert call["system"] == postmortem.system_prompt() and call["schema"] is postmortem.PM_SCHEMA
    assert call["user"].startswith("Pacote do caso (JSON):\n")
    sent = json.loads(call["user"].split("\n", 1)[1])
    assert sent["depois"]["caminho_do_preco"]["invalidacao_tocada_em"] == "2026-10-01T15:00:00+00:00"
    # o caso dura 3 horas, sem nenhum fechamento das 16h NY no meio: nada de referências (seria olhar para o futuro)
    assert sent["depois"]["referencias"]["disponivel"] is False and sent["depois"]["referencias_notaveis"] == []

    saved = store.latest_for_entry(eid, with_package=True)
    assert saved["package"] == sent and saved["result"] == pm["result"] and saved["model"] == "anthropic/claude-sonnet-5.5"


def long_bars(entry, now):
    idx = pd.date_range("2026-10-01 12:00", "2026-10-05 16:00", freq="h", tz="UTC")
    frame = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1.0}, index=idx)
    frame.loc[pd.Timestamp("2026-10-05 15:00", tz="UTC"), ["Low", "Close"]] = 94.5
    return frame, "1h"


def test_a_multi_day_case_gets_the_reference_moves_and_notable_ones_are_listed():
    eid = add_entry(closed_at="2026-10-05T15:00:00+00:00")
    chat = FakeChat(good(causa_principal="evento_macro", visibilidade="so_ficou_claro_depois", o_que_era_visivel=[], o_que_so_ficou_claro_depois=["S&P caiu 4%"], evidencias=[{"campo": "depois.referencias.instrumentos.sp500.variacao", "valor": "-4", "leitura": "queda do índice"}]))
    pm = run(eid, chat, fetch_bars=long_bars)
    sent = json.loads(chat.calls[0]["user"].split("\n", 1)[1])
    refs = sent["depois"]["referencias"]
    assert refs["disponivel"] and refs["instrumentos"]["sp500"]["variacao"] == -4.0
    assert sent["depois"]["referencias_notaveis"] == ["sp500"]
    assert pm["checks"] == [] and pm["result"]["evidencias"][0]["verificada"] is True  # evento macro com referência notável: sem aviso


def test_rerunning_keeps_history_but_the_latest_wins_and_delete_cascades():
    eid = add_entry()
    first = run(eid, FakeChat(good(causa_principal="sem_causa_identificavel", visibilidade="nao_se_aplica", o_que_era_visivel=[])))
    second = run(eid, FakeChat(good(causa_principal="evento_macro")))
    assert second["id"] > first["id"]
    assert store.latest_for_entry(eid)["result"]["causa_principal"] == "evento_macro"
    assert list(store.latest_by_entry()) == [eid]
    assert store.delete_for_entry(eid) == 2 and store.latest_for_entry(eid) is None


def test_run_refuses_what_it_cannot_do_with_clear_errors(monkeypatch):
    with pytest.raises(postmortem.PostmortemError) as e:
        run(999)
    assert e.value.kind == "nao_encontrado"
    ok = add_entry(status="alvo", closed_at="2026-10-02T12:00:00+00:00", r_multiple=2.0)
    with pytest.raises(postmortem.PostmortemError) as e:
        run(ok)
    assert e.value.kind == "nao_elegivel"

    eid = add_entry()
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with pytest.raises(AIError) as e:
        postmortem.run(eid, fetch_bars=fake_bars, load_closes=closes, now=NOW)  # sem chat e sem chave
    assert e.value.kind == "sem_chave"

    def broken(entry, now):
        raise ProviderError("Yahoo fora do ar")

    with pytest.raises(postmortem.PostmortemError) as e:
        run(eid, fetch_bars=broken)
    assert e.value.kind == "sem_caminho" and "Yahoo" in e.value.message
    with pytest.raises(postmortem.PostmortemError) as e:
        run(eid, fetch_bars=lambda entry, now: (hourly().iloc[0:0], "1h"))
    assert e.value.kind == "sem_caminho"
    assert store.latest_for_entry(eid) is None  # nada foi gravado nas falhas


def test_model_errors_and_invalid_answers_are_not_saved():
    eid = add_entry()
    with pytest.raises(AIError) as e:
        run(eid, FakeChat(error=AIError("creditos", "Sem saldo")))
    assert e.value.kind == "creditos"
    with pytest.raises(AIError) as e:
        run(eid, FakeChat(good(causa_principal="azar")))
    assert e.value.kind == "resposta_invalida" and "lista fixa" in e.value.message
    assert store.latest_for_entry(eid) is None


def test_unverified_citations_and_inapplicable_causes_come_back_as_checks():
    eid = add_entry(decision="nao_entrei")
    out = good(causa_principal="entrada_tardia", evidencias=[{"campo": "depois.nao_existe", "valor": "9", "leitura": "x"}])
    pm = run(eid, FakeChat(out))
    kinds = {c["tipo"] for c in pm["checks"]}
    assert {"nao_se_aplica", "citacao"} <= kinds
    assert pm["result"]["evidencias"][0]["verificada"] is False


def test_early_exit_alone_makes_a_thesis_that_hit_the_target_eligible():
    eid = add_entry(status="alvo", early_exit_at="2026-10-01T14:00:00+00:00", early_exit_price=99.0, early_exit_r=-0.2)
    pm = run(eid)
    assert pm["trigger"] == "saida_antecipada"


# ---------- API ----------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(postmortem, "default_fetch_bars", fake_bars)
    monkeypatch.setattr(postmortem.corr_store, "load_closes", closes)
    monkeypatch.setattr(ai_client, "chat_json", FakeChat())
    with TestClient(app) as c:
        yield c


def test_api_overview_postmortem_and_listing(client):
    eid = add_entry()
    skipped = add_entry(status="alvo", closed_at="2026-10-02T12:00:00+00:00", r_multiple=2.0)

    ov = client.get("/api/memory").json()
    assert ov["pendentes"] == 1 and [e["id"] for e in ov["elegiveis"]] == [eid]
    assert ov["elegiveis"][0]["trigger"] == "invalidada" and ov["elegiveis"][0]["postmortem"] is None
    assert ov["causas"]["versao"] == "causas-v1" and len(ov["causas"]["lista"]) == 6
    assert ov["ia"]["configured"] is True and ov["ia"]["prompt_version"] == "pm-v1"

    listing = {e["id"]: e for e in client.get("/api/journal").json()}
    assert listing[eid]["postmortem_trigger"] == "invalidada" and listing[eid]["postmortem"] is None
    assert listing[skipped]["postmortem_trigger"] is None

    assert client.post(f"/api/memory/postmortem/{skipped}").status_code == 400
    assert client.post("/api/memory/postmortem/999").status_code == 404
    made = client.post(f"/api/memory/postmortem/{eid}")
    assert made.status_code == 200 and made.json()["result"]["causa_principal"] == "indicador_deu_ruido"

    ov = client.get("/api/memory").json()
    assert ov["pendentes"] == 0 and ov["elegiveis"][0]["postmortem"]["causa_principal"] == "indicador_deu_ruido"
    assert ov["distribuicao_das_causas"]["n"] == 1 and ov["distribuicao_das_causas"]["itens"][0]["causa"] == "indicador_deu_ruido"
    listed = {e["id"]: e for e in client.get("/api/journal").json()}
    assert listed[eid]["postmortem"]["causa_principal"] == "indicador_deu_ruido" and listed[eid]["postmortem"]["avisos"] == 0

    full = client.get(f"/api/memory/postmortem/{eid}").json()
    assert full["package"]["caso"]["simbolo"] == "NVDA"
    assert client.get(f"/api/memory/postmortem/{skipped}").status_code == 404

    assert client.delete(f"/api/journal/{eid}").status_code == 204
    assert client.get(f"/api/memory/postmortem/{eid}").status_code == 404  # o pós-mortem vai junto com o registro


def test_api_errors_map_to_http_codes(client, monkeypatch):
    eid = add_entry()
    monkeypatch.setattr(ai_client, "chat_json", FakeChat(error=AIError("creditos", "Sem saldo na OpenRouter.")))
    r = client.post(f"/api/memory/postmortem/{eid}")
    assert r.status_code == 402 and "Sem saldo" in r.json()["detail"]
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    assert client.post(f"/api/memory/postmortem/{eid}").status_code == 400
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")

    def broken(entry, now):
        raise ProviderError("sem rede")

    monkeypatch.setattr(postmortem, "default_fetch_bars", broken)
    assert client.post(f"/api/memory/postmortem/{eid}").status_code == 502


def test_api_prompt_endpoint_shows_the_exact_text(client):
    body = client.get("/api/memory/prompt").json()
    assert body["version"] == "pm-v1" and body["fingerprint"] == PM_V1_FINGERPRINT
    assert body["prompt"] == postmortem.system_prompt() and body["schema"] == postmortem.PM_SCHEMA
