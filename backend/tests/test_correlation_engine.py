import numpy as np
import pandas as pd
import pytest

from app.correlation import engine
from app.correlation.universe import Instrument

FIXED = [("^GSPC", "S&P 500"), ("DX-Y.NYB", "DXY")]
CANDS = [
    Instrument("^VIX", "VIX", "Risco e índices"),
    Instrument("RAND", "Aleatório", "Risco e índices"),
    Instrument("GC=F", "Ouro", "Commodities"),
    Instrument("XLK", "Tecnologia (XLK)", "Setores (EUA)"),
    Instrument("^TNX", "Juro 10 anos", "Dólar e juros"),
]


def make_closes(n=420, seed=5):
    """Alvo ~ 1,5 × mercado; S&P = mercado; VIX ~ -3 × mercado; ouro ~ -0,5 × dólar; DXY e RAND independentes."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    m = rng.normal(0.0004, 0.01, n)
    dxy = rng.normal(0, 0.004, n)
    ret = {
        engine.TARGET: 1.5 * m + rng.normal(0, 0.006, n),
        "^GSPC": m,
        "DX-Y.NYB": dxy,
        "^VIX": -3 * m + rng.normal(0, 0.01, n),
        "GC=F": -0.5 * dxy + rng.normal(0, 0.006, n),
        "XLK": 1.2 * m + rng.normal(0, 0.003, n),
        "RAND": rng.normal(0, 0.01, n),
    }
    closes = pd.DataFrame({k: 100 * np.cumprod(1 + v) for k, v in ret.items()}, index=idx)
    closes["^TNX"] = 4 + np.cumsum(rng.normal(0, 0.03, n))
    return closes


def set_tail(closes, col, end_factor, k=20):
    """Faz `col` andar em linha reta, nos últimos k fechamentos, até end_factor × o fechamento de k+1 dias atrás
    (o movimento de 20 dias fica exato). Atribuição direta: no pandas 3 a atribuição encadeada não funciona."""
    pos = closes.columns.get_loc(col)
    base = closes[col].iloc[-k - 1]
    closes.iloc[-k:, pos] = base * np.linspace(1, end_factor, k + 1)[1:]


def panel(closes=None, mech=lambda s: False, exclude=frozenset()):
    return engine.build_panel(make_closes() if closes is None else closes, CANDS, FIXED, mech, exclude)


def row(out, symbol):
    for r in out["fixed"]:
        if r["symbol"] == symbol:
            return r
    for g in out["discovered"]:
        for r in g["items"]:
            if r["symbol"] == symbol:
                return r
    return None


def test_market_reference_is_stable_and_unrelated_dollar_is_not():
    out = panel()
    spx, dxy = row(out, "^GSPC"), row(out, "DX-Y.NYB")
    assert spx["status"] == "estável" and spx["corr_full"] > 0.7 and spx["stability"] >= 0.8
    assert spx["beta"] == pytest.approx(1.5, abs=0.25)
    assert dxy["status"] == "sem relação estável"


def test_discovered_groups_and_signs():
    out = panel()
    names = [g["name"] for g in out["discovered"]]
    assert names == ["Risco e índices", "Commodities", "Setores (EUA)", "Dólar e juros"]
    vix = row(out, "^VIX")
    assert vix["corr_full"] < -0.6 and vix["status"] == "estável"
    assert row(out, "RAND")["status"] == "sem relação estável"
    # dentro do grupo, ordenado por |correlação|
    risk = next(g for g in out["discovered"] if g["name"] == "Risco e índices")["items"]
    assert abs(risk[0]["corr_full"]) >= abs(risk[1]["corr_full"])


def test_mechanical_relations_are_flagged_and_do_not_count_as_stable():
    out = panel(mech=lambda s: s == "XLK")
    xlk = row(out, "XLK")
    assert xlk["mechanical"] is True and xlk["status"] == "mecânica"


def test_excluded_symbols_are_skipped():
    out = panel(exclude={"^VIX", "DX-Y.NYB"})
    assert row(out, "^VIX") is None
    assert [r["symbol"] for r in out["fixed"]] == ["^GSPC"]


def test_yield_candidates_use_point_changes():
    out = panel()
    tnx = row(out, "^TNX")
    assert tnx is not None and tnx["other_unit"] == "pts"


def test_parecer_uses_only_non_mechanical_references():
    both = panel()["parecer"]
    assert both["refs_used"] == ["S&P 500", "DXY"]
    assert any("S&P 500" in line for line in both["lines"])
    assert both["r2"] is not None and both["r2"] >= both["r2_first"] - 1e-9
    assert isinstance(both["z20"], float)

    only_spx = panel(mech=lambda s: s == "DX-Y.NYB")["parecer"]
    assert only_spx["refs_used"] == ["S&P 500"]
    assert any("mecânica" in line for line in only_spx["lines"])


def test_parecer_describes_a_divergence_in_the_last_20_days():
    closes = make_closes()
    set_tail(closes, engine.TARGET, 0.85)  # ativo cai 15% em 20 dias
    p = panel(closes)["parecer"]
    assert p["gap20_pp"] < -5
    assert p["z20"] < -2
    assert any("divergência forte" in line for line in p["lines"])


def test_parecer_does_not_compare_when_references_explain_almost_nothing():
    closes = make_closes()
    closes[engine.TARGET] = closes["RAND"].to_numpy()  # ativo sem relação com S&P nem DXY
    p = panel(closes)["parecer"]
    assert p["r2"] < engine.MIN_R2_FOR_GAP
    assert any("explicam pouco" in line for line in p["lines"])
    assert not any("O modelo esperava" in line for line in p["lines"])


def test_charts_shapes():
    ch = panel()["charts"]
    reb = ch["rebased"]
    assert len(reb["dates"]) == engine.REBASE_DAYS
    assert all(abs(v[0] - 100) < 1e-6 for v in reb["series"].values())
    assert set(reb["series"]) == {"Ativo", "S&P 500", "DXY"}
    assert set(ch["rolling"]["series"]) == {"S&P 500", "DXY"}
    sc = ch["scatter"]
    assert sc["ref"] == "S&P 500" and len(sc["recent"]) == engine.RECENT
    assert sc["slope"] == pytest.approx(1.5, abs=0.25)


def test_perfectly_correlated_pair():
    closes = make_closes()
    closes["CLONE"] = closes[engine.TARGET]
    r = engine.pair_row(closes, "CLONE")
    assert r["corr_full"] == pytest.approx(1.0) and r["stability"] == 1.0 and r["beta"] == pytest.approx(1.0)


def test_too_few_observations_returns_none():
    assert engine.pair_row(make_closes(n=60), "^GSPC") is None
    assert engine.pair_row(make_closes(), "NAO_EXISTE") is None


def test_agreement_flag_follows_sign_of_correlation():
    closes = make_closes()
    set_tail(closes, "^GSPC", 1.10)  # S&P sobe 10%
    set_tail(closes, engine.TARGET, 0.90)  # ativo (correlação positiva) cai 10%
    assert row(panel(closes), "^GSPC")["agree"] == "divergem"
    set_tail(closes, engine.TARGET, 1.10)  # agora os dois sobem
    assert row(panel(closes), "^GSPC")["agree"] == "concordam"


def test_classify_requires_weekly_agreement_and_threshold():
    ok = {"corr_full": 0.5, "stability": 0.9, "weekly": 0.4}
    assert engine.classify(ok, False) == "estável"
    assert engine.classify({**ok, "weekly": -0.1}, False) == "sem relação estável"
    assert engine.classify({**ok, "stability": 0.7}, False) == "sem relação estável"
    assert engine.classify({**ok, "corr_full": 0.2}, False) == "sem relação estável"
    assert engine.classify(ok, True) == "mecânica"
