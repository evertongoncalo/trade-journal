import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.alerts import store as alert_store
from app.analysis.state_prob import wilson
from app.main import app
from app.review import blocks, engine


def row(i, status, direction="alta", decision="entrei", market="acoes", symbol="AAA", setup="", snap=None, early=False):
    return {
        "id": i, "created_at": f"2026-10-{(i % 28) + 1:02d}T12:00:00+00:00", "market": market, "symbol": symbol,
        "decision": decision, "direction": direction, "status": status, "setup": setup,
        "snapshot_json": json.dumps(snap or {}), "early_exit_at": "2026-10-20T12:00:00+00:00" if early else None,
    }


def rows_of(spec, **kw):
    """spec: lista de (status, quantidade); ids sequenciais."""
    out, i = [], 1
    for status, n in spec:
        for _ in range(n):
            out.append(row(i, status, **kw))
            i += 1
    return out


# --- blocos de código -------------------------------------------------------------------------------------------

def test_block_probabilidade_e_tendencia_e_macd():
    snap = {
        "probability": {"label": "sem dados"},
        "indicators": {"trend": "lateral", "macd_hist": -0.2},
    }
    d = blocks.derive(snap)
    assert d["probabilidade"] == "sem_dados"
    assert d["tendencia"] == "indistinta"
    assert d["macd"] == "baixa"
    up = blocks.derive({"probability": {"label": "alta"}, "indicators": {"trend": "alta", "macd_hist": 0.5}})
    assert (up["probabilidade"], up["tendencia"], up["macd"]) == ("alta", "alta", "alta")
    assert blocks.derive({"indicators": {"trend": "baixa", "macd_hist": None}})["macd"] == "sem_dados"
    assert blocks.derive({"indicators": {"trend": "indefinida", "macd_hist": 0.0}})["tendencia"] == "sem_dados"


def test_block_ausente_e_none_nao_zero():
    d = blocks.derive({})
    assert all(v is None for v in d.values())  # registro antigo: o bloco não foi guardado


def test_block_price_action():
    f = lambda s: blocks.derive({"price_action": {"estrutura": s}})["price_action"]
    assert f("topos e fundos ascendentes") == "alta"
    assert f("topos e fundos descendentes") == "baixa"
    assert f("misto (topos e fundos em direções diferentes)") == "indistinta"
    assert f("indefinida") == "sem_dados"


def test_block_correlacao_usa_sinal_da_correlacao_vezes_movimento_da_referencia():
    def corr(**ref):
        return blocks.derive({"correlation": {"^GSPC": ref, "DX-Y.NYB": ref}})

    base = {"status": "estável", "other_unit": "%"}
    assert corr(**base, corr_full=0.6, move20_other=3.0)["corr_sp500"] == "alta"
    assert corr(**base, corr_full=0.6, move20_other=-3.0)["corr_sp500"] == "baixa"
    assert corr(**base, corr_full=-0.5, move20_other=2.0)["corr_dxy"] == "baixa"  # correlação negativa inverte
    assert corr(**base, corr_full=-0.5, move20_other=-2.0)["corr_dxy"] == "alta"
    assert corr(**base, corr_full=0.6, move20_other=0.2)["corr_sp500"] == "indistinta"  # movimento desprezível
    assert corr(status="estável", other_unit="pts", corr_full=0.6, move20_other=0.2)["corr_sp500"] == "alta"
    assert corr(status="sem relação estável", corr_full=0.9, move20_other=5.0)["corr_sp500"] == "indistinta"
    assert corr(status="sem dados")["corr_sp500"] == "sem_dados"
    assert corr(status="estável", corr_full=None, move20_other=None)["corr_sp500"] == "sem_dados"
    assert corr(status="mecânica", corr_full=-0.98, move20_other=2.0)["corr_dxy"] is None  # não se aplica


def test_correlacao_ausente_do_snapshot_e_none():
    d = blocks.derive({"correlation": {"^GSPC": {"status": "estável", "corr_full": 0.5, "move20_other": 2, "other_unit": "%"}}})
    assert d["corr_sp500"] == "alta"
    assert d["corr_dxy"] is None  # o alvo era o próprio DXY (ou o painel não guardou)


def test_ai_lenses_traduz_inclinacao():
    snap = {"ai": {"lenses": {"Macro": {"inclinacao": "para_baixa"}, "Price action": {"inclinacao": "para_alta"},
                              "Indicadores": {"inclinacao": "indistinta"}, "Fund": {"inclinacao": "xyz"}}}}
    assert blocks.ai_lenses(snap) == {"Macro": "baixa", "Price action": "alta", "Indicadores": "indistinta", "Fund": "sem_dados"}
    assert blocks.ai_lenses({}) == {}
    assert blocks.ai_lenses({"ai": None}) == {}


# --- estatística de grupo ---------------------------------------------------------------------------------------

def test_cell_conta_e_exclui_expiradas_e_abertas_da_taxa():
    c = engine.cell(rows_of([("alvo", 6), ("invalidada", 4), ("expirada", 3), ("aberta", 2)]))
    assert (c["registros"], c["alvo"], c["invalidada"], c["expirada"], c["aberta"], c["fechadas"]) == (15, 6, 4, 3, 2, 10)
    assert c["taxa_acerto"] == pytest.approx(0.6)
    assert c["ic95"] == pytest.approx(list(wilson(6, 10)))
    assert c["amostra"] == "pequena"
    assert c["ids"] == list(range(1, 16))


def test_cell_sem_fechadas_nao_inventa_taxa():
    c = engine.cell(rows_of([("aberta", 2), ("expirada", 1)]))
    assert c["taxa_acerto"] is None and c["ic95"] is None and c["amostra"] == "insuficiente"
    assert engine.cell([])["registros"] == 0


@pytest.mark.parametrize("n,label", [(0, "insuficiente"), (9, "insuficiente"), (10, "pequena"), (29, "pequena"), (30, "ok")])
def test_rotulo_de_amostra(n, label):
    assert engine.sample_label(n) == label


def test_difference_distinguivel_a_favor_do_primeiro():
    a = engine.cell(rows_of([("alvo", 24), ("invalidada", 6)]))
    b = engine.cell(rows_of([("alvo", 12), ("invalidada", 18)]))
    d = engine.difference(a, b)
    (la, ua), (lb, ub) = wilson(24, 30), wilson(12, 30)
    assert d["pp"] == pytest.approx(40.0)
    assert d["ic95_pp"][0] == pytest.approx(((0.8 - 0.4) - ((0.8 - la) ** 2 + (ub - 0.4) ** 2) ** 0.5) * 100)
    assert d["ic95_pp"][1] == pytest.approx(((0.8 - 0.4) + ((ua - 0.8) ** 2 + (0.4 - lb) ** 2) ** 0.5) * 100)
    assert d["leitura"] == "a_maior"
    assert engine.difference(b, a)["leitura"] == "b_maior"


def test_difference_indistinta_quando_o_intervalo_inclui_zero():
    a = engine.cell(rows_of([("alvo", 16), ("invalidada", 14)]))
    b = engine.cell(rows_of([("alvo", 14), ("invalidada", 16)]))
    assert engine.difference(a, b)["leitura"] == "indistinta"


def test_difference_sem_dados_com_amostra_pequena_ou_vazia():
    big = engine.cell(rows_of([("alvo", 20), ("invalidada", 10)]))
    tiny = engine.cell(rows_of([("alvo", 0), ("invalidada", 5)]))  # 5 fechadas: diferença enorme, mas sem amostra
    assert engine.difference(big, tiny)["leitura"] == "sem dados"
    assert engine.difference(big, engine.cell([]))["pp"] is None


# --- recortes --------------------------------------------------------------------------------------------------

def test_concordancia_compara_com_a_direcao_da_tese():
    rows = [
        row(1, "alvo", direction="baixa", snap={"price_action": {"estrutura": "topos e fundos descendentes"}}),  # a favor
        row(2, "invalidada", direction="alta", snap={"price_action": {"estrutura": "topos e fundos descendentes"}}),  # contra
        row(3, "alvo", direction="alta", snap={"price_action": {"estrutura": "topos e fundos ascendentes"}}),  # a favor
        row(4, "expirada", direction="alta", snap={"price_action": {"estrutura": "misto (x)"}}),  # sem inclinação
        row(5, "alvo", direction="alta", snap={}),  # bloco não guardado
    ]
    pa = next(b for b in engine.by_block(rows) if b["bloco"] == "price_action")
    assert pa["a_favor"]["ids"] == [1, 3] and pa["a_favor"]["alvo"] == 2
    assert pa["contra"]["ids"] == [2] and pa["contra"]["invalidada"] == 1
    assert pa["sem_inclinacao"]["ids"] == [4]
    assert pa["sem_registro"] == 1
    assert pa["regra"]


def test_todos_os_blocos_aparecem_mesmo_sem_dados():
    out = engine.by_block([])
    assert [b["bloco"] for b in out] == [k for k, _, _ in blocks.BLOCKS]
    assert all(b["diferenca"]["leitura"] == "sem dados" for b in out)


def test_lentes_de_ia_e_versoes():
    ai = lambda stance, v="v1": {"ai": {"prompt_version": v, "model": "m", "lenses": {"Macro": {"inclinacao": stance}}}}
    rows = [
        row(1, "alvo", snap=ai("para_alta")),
        row(2, "invalidada", snap=ai("para_baixa")),
        row(3, "alvo", snap=ai("para_alta", v="v2")),
        row(4, "alvo"),
    ]
    out = engine.by_lens(rows)
    assert out["registros_com_ia"] == 3
    assert [v["registros"] for v in out["versoes"]] == [2, 1]
    macro = out["lentes"][0]
    assert macro["lente"] == "Macro"
    assert macro["a_favor"]["ids"] == [1, 3] and macro["contra"]["ids"] == [2] and macro["sem_registro"] == 1


def test_decisao_certa_inverte_para_quem_ficou_de_fora():
    rows = (
        rows_of([("alvo", 3), ("invalidada", 1)], decision="entrei")
        + [row(10 + i, s, decision="nao_entrei") for i, s in enumerate(["invalidada", "invalidada", "alvo"])]
        + [row(20, "invalidada", decision="observando", early=False)]
    )
    out = engine.by_decision(rows)
    by = {line["chave"]: line for line in out["linhas"]}
    assert by["entrei"]["decisao_certa"]["acertos"] == 3 and by["entrei"]["decisao_certa"]["fechadas"] == 4
    assert by["nao_entrei"]["decisao_certa"]["acertos"] == 2 and by["nao_entrei"]["decisao_certa"]["fechadas"] == 3
    assert by["observando"]["decisao_certa"]["acertos"] == 1
    assert out["entrei_vs_fora"]["entrei"]["registros"] == 4
    assert out["entrei_vs_fora"]["fora"]["registros"] == 4
    assert out["entrei_vs_fora"]["diferenca"]["leitura"] == "sem dados"  # amostras pequenas


def test_saida_antecipada_so_conta_quem_entrou():
    rows = [
        row(1, "alvo", early=True),
        row(2, "invalidada", early=True),
        row(3, "aberta", early=True),
        row(4, "alvo", early=False),
        row(5, "alvo", decision="nao_entrei", early=True),  # nunca deveria existir, mas não entra na conta
    ]
    se = engine.by_decision(rows)["saida_antecipada"]
    assert se["registros"] == 3
    assert (se["depois"]["alvo"], se["depois"]["invalidada"], se["depois"]["aberta"]) == (1, 1, 1)


def test_por_setup_separa_nomes_e_conta_o_registro_em_cada_um():
    rows = [
        row(1, "alvo", setup="Rompimento + Volume"),
        row(2, "invalidada", setup="Rompimento"),
        row(3, "alvo", setup=""),
    ]
    got = {g["chave"]: g["registros"] for g in engine._group(rows, engine._setup_names)}
    assert got == {"Rompimento": 2, "Volume": 1, "(sem setup)": 1}


# --- alertas ---------------------------------------------------------------------------------------------------

def alert(i, kind, status="disparado", response=None, entry_id=None):
    return {"id": i, "kind": kind, "status": status, "response": response, "entry_id": entry_id}


def test_alertas_resposta_por_tipo_e_desfecho_so_da_entrada():
    entries = [row(1, "alvo"), row(2, "invalidada"), row(3, "aberta")]
    alerts = [
        alert(1, "entrada", response="entrei", entry_id=1),
        alert(2, "entrada", response="entrei", entry_id=2),
        alert(3, "entrada", response="ignorei", entry_id=3),
        alert(4, "entrada", response=None, entry_id=1),
        alert(5, "alvo", response="entrei", entry_id=1),  # circular: não entra no desfecho
        alert(6, "avulso", response="observando"),
        alert(7, "avulso", status="ativo"),
        alert(8, "invalidacao", status="cancelado", entry_id=2),
        alert(9, "entrada", response="entrei", entry_id=999),  # registro excluído
    ]
    out = engine.alerts_review(alerts, entries)
    assert (out["criados"], out["disparados"], out["cancelados"], out["sem_resposta"]) == (9, 7, 1, 1)
    kinds = {k["tipo"]: k for k in out["por_tipo"]}
    assert (kinds["entrada"]["entrei"], kinds["entrada"]["ignorei"], kinds["entrada"]["sem_resposta"]) == (3, 1, 1)
    assert kinds["avulso"]["observando"] == 1 and kinds["avulso"]["criados"] == 2 and kinds["avulso"]["disparados"] == 1
    outcome = {o["chave"]: o for o in out["entrada_por_resposta"]}
    assert outcome["entrei"]["ids"] == [1, 2] and (outcome["entrei"]["alvo"], outcome["entrei"]["invalidada"]) == (1, 1)
    assert outcome["ignorei"]["ids"] == [3] and outcome["ignorei"]["aberta"] == 1
    assert outcome["observando"]["registros"] == 0


def test_entrada_repetida_para_o_mesmo_registro_conta_uma_vez():
    entries = [row(1, "alvo")]
    alerts = [alert(1, "entrada", response="entrei", entry_id=1), alert(2, "entrada", response="entrei", entry_id=1)]
    out = engine.alerts_review(alerts, entries)
    assert next(o for o in out["entrada_por_resposta"] if o["chave"] == "entrei")["registros"] == 1


# --- avisos e API ----------------------------------------------------------------------------------------------

def test_avisos_pedem_cautela_com_amostra_pequena():
    out = engine.build(rows_of([("alvo", 3), ("invalidada", 2)]), [])
    assert any("anedota" in a for a in out["avisos"])
    assert out["amostra"]["ativos_distintos"] == 1
    assert out["regras_versao"] == blocks.RULES_VERSION
    big = engine.build(rows_of([("alvo", 20), ("invalidada", 20)]), [])
    assert not any("anedota" in a for a in big["avisos"])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    with TestClient(app) as c:
        yield c


def _insert(**kw):
    data = dict(
        created_at="2026-10-01T12:00:00+00:00", market="acoes", symbol="NVDA", decision="entrei", direction="alta",
        entry_price=100, invalidation=95, target=110, horizon_days=5, thesis="", setup="Rompimento",
        snapshot_json=json.dumps({"indicators": {"trend": "alta", "macd_hist": 0.3}}), status="alvo",
    )
    data.update(kw)
    return db.insert_entry(data)


def test_api_vazia_devolve_estrutura_sem_quebrar(client):
    body = client.get("/api/review").json()
    assert body["amostra"]["registros"] == 0 and body["amostra"]["taxa_acerto"] is None
    assert len(body["por_bloco"]) == len(blocks.BLOCKS)
    assert body["por_decisao"]["linhas"][0]["chave"] == "entrei"
    assert body["alertas"]["criados"] == 0
    assert body["avisos"]


def test_api_com_registros_e_alertas(client):
    e1 = _insert()
    _insert(symbol="BTCUSDT", market="cripto", status="invalidada", decision="nao_entrei")
    a = alert_store.create("acoes", "NVDA", 100.0, "abaixo", kind="entrada", entry_id=e1)
    alert_store.mark_triggered(a["id"], "2026-10-01T13:00:00+00:00", 99.5)
    alert_store.respond(a["id"], "entrei")

    body = client.get("/api/review").json()
    assert body["amostra"]["registros"] == 2 and body["amostra"]["ativos_distintos"] == 2
    assert {m["chave"] for m in body["por_mercado"]} == {"acoes", "cripto"}
    assert body["por_setup"][0]["chave"] == "Rompimento"
    tendencia = next(b for b in body["por_bloco"] if b["bloco"] == "tendencia")
    assert tendencia["a_favor"]["ids"] == [1, 2] and tendencia["sem_registro"] == 0
    resp = next(o for o in body["alertas"]["entrada_por_resposta"] if o["chave"] == "entrei")
    assert resp["ids"] == [e1] and resp["alvo"] == 1
    json.dumps(body)  # serializável (sem NaN)
