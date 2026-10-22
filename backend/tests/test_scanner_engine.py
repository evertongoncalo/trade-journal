import numpy as np
import pandas as pd

from app.scanner import engine
from app.scanner.conditions import normalize_definition


def ohlcv(n=300, drift=0.0015, seed=1, volume=1e6, start_price=50.0):
    rng = np.random.default_rng(seed)
    close = start_price * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": close, "High": close * 1.004, "Low": close * 0.996, "Close": close, "Volume": volume}, index=idx
    )


def setup(required=(), confirmations=(), min_conf=0, markets=("acoes",), direction="alta", filters=None, sid=1):
    definition = normalize_definition(
        {
            "required": [{"type": t, "params": p} for t, p in required],
            "confirmations": [{"type": t, "params": p} for t, p in confirmations],
            "min_confirmations": min_conf,
            "filters": filters or {},
        }
    )
    return {"id": sid, "name": f"setup{sid}", "direction": direction, "markets": list(markets), "definition": definition}


def test_features_adds_derived_columns():
    d = engine.features(ohlcv())
    for col in ("rsi14", "macd_hist", "sma20", "sma50", "atr_pct", "bb_pctb", "vol_ratio"):
        assert col in d.columns
    assert d["vol_ratio"].iloc[-1] == 1.0  # volume constante
    assert 0 <= d["rsi14"].iloc[-1] <= 100


def test_features_without_volume_has_no_ratio():
    df = ohlcv(volume=0.0)
    assert not engine.has_volume(df)
    assert engine.features(df)["vol_ratio"].isna().all()


def test_required_conditions_must_all_pass():
    d = engine.features(ohlcv(drift=0.003))  # tendência forte de alta
    both = setup(required=[("trend_up", {}), ("close_above_sma", {"n": 20})])
    assert engine.evaluate_setup(both["definition"], d, True)["required"]
    impossible = setup(required=[("trend_up", {}), ("rsi_between", {"lo": 0, "hi": 1})])
    assert engine.evaluate_setup(impossible["definition"], d, True) is None


def test_confirmations_need_the_minimum():
    d = engine.features(ohlcv(drift=0.003))
    base = [("trend_up", {})]
    two_of_three = setup(
        required=base, confirmations=[("up_day", {}), ("down_day", {}), ("close_above_sma", {"n": 20})], min_conf=2
    )
    res = engine.evaluate_setup(two_of_three["definition"], d, True)
    assert res is not None and res["confirmations_applicable"] == 3 and len(res["confirmations"]) >= 2
    too_many = setup(required=base, confirmations=[("down_day", {}), ("rsi_between", {"lo": 0, "hi": 1})], min_conf=1)
    assert engine.evaluate_setup(too_many["definition"], d, True) is None


def test_volume_conditions_are_ignored_when_the_market_has_no_volume():
    d = engine.features(ohlcv(drift=0.003, volume=0.0))
    s = setup(required=[("trend_up", {}), ("volume_ratio_above", {"x": 5})], confirmations=[("volume_ratio_above", {"x": 5})], min_conf=1)
    res = engine.evaluate_setup(s["definition"], d, volume_ok=False)
    assert res is not None
    assert len(res["not_applicable"]) == 2 and res["confirmations_applicable"] == 0
    # com volume disponível, a mesma condição (5× a média) reprova
    d2 = engine.features(ohlcv(drift=0.003))
    assert engine.evaluate_setup(s["definition"], d2, volume_ok=True) is None


def test_filters_apply_only_to_stocks():
    d = engine.features(ohlcv(start_price=3.0, drift=0.0, volume=1000))
    f = {"min_price": 5, "min_dollar_volume": 1_000_000}
    assert engine.passes_filters(d, "acoes", f) is False
    assert engine.passes_filters(d, "cripto", f) is True
    assert engine.passes_filters(d, "forex", f) is True
    rich = engine.features(ohlcv(start_price=100.0, drift=0.0, volume=1e6))
    assert engine.passes_filters(rich, "acoes", f) is True


def test_evaluate_symbol_returns_hits_with_details():
    df = ohlcv(drift=0.003)
    hits = engine.evaluate_symbol(
        "acoes", "AAA", df,
        [setup(required=[("trend_up", {})], sid=1), setup(required=[("trend_down", {})], sid=2)],
    )
    assert [h["setup_id"] for h in hits] == [1]
    h = hits[0]
    assert h["symbol"] == "AAA" and h["market"] == "acoes" and h["direction"] == "alta"
    assert h["details"]["trend"] == "alta" and h["details"]["as_of"] == df.index[-1].date().isoformat()
    assert h["details"]["required"] == ["Tendência de alta (preço > MM20 > MM50)"]


def test_evaluate_symbol_respects_market_and_history():
    df = ohlcv(drift=0.003)
    s = setup(required=[("trend_up", {})], markets=("cripto",))
    assert engine.evaluate_symbol("acoes", "AAA", df, [s]) == []
    assert engine.evaluate_symbol("cripto", "BBB", df, [s])
    assert engine.evaluate_symbol("cripto", "BBB", df.iloc[:30], [s]) == []  # histórico curto


def test_forex_hit_has_no_volume_ratio():
    df = ohlcv(drift=0.003, volume=0.0)
    hits = engine.evaluate_symbol("forex", "EURUSD", df, [setup(required=[("trend_up", {})], markets=("forex",))])
    assert hits and hits[0]["details"]["volume_ratio"] is None
