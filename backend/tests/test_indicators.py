import numpy as np
import pandas as pd
import pytest

from app.analysis.indicators import atr, bollinger, macd, rma, rsi, snapshot, trend_of

# Série de fechamentos de um exemplo clássico de RSI(14) de Wilder (planilha de referência do StockCharts).
CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
    45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
    45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
]
# RSI de referência a partir da 15ª barra (índice 14).
REFERENCE = {14: 70.53, 15: 66.32, 16: 66.55, 17: 69.41, 18: 66.36, 19: 57.97}


def test_rsi_matches_wilder_reference():
    r = rsi(pd.Series(CLOSES))
    assert r.iloc[:14].isna().all()
    for i, expected in REFERENCE.items():
        assert r.iloc[i] == pytest.approx(expected, abs=0.1), f"índice {i}"


def test_rsi_extremes():
    up = pd.Series(np.arange(1.0, 41.0))
    assert rsi(up).iloc[-1] == 100.0
    assert rsi(up[::-1].reset_index(drop=True)).iloc[-1] == 0.0
    assert rsi(pd.Series([10.0] * 40)).iloc[-1] == 50.0


def test_rsi_bounds():
    rng = np.random.default_rng(1)
    r = rsi(pd.Series(100 + rng.normal(0, 1, 500).cumsum())).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rma_seed_is_simple_average():
    out = rma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert out.iloc[:2].isna().all()
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx((2.0 * 2 + 4.0) / 3)


def test_macd_histogram_is_line_minus_signal():
    close = pd.Series(100 + np.random.default_rng(2).normal(0, 1, 200).cumsum())
    line, sig, hist = macd(close)
    assert (hist - (line - sig)).abs().max() < 1e-12


def test_atr_of_constant_range():
    n = 40
    df = pd.DataFrame({"High": [11.0] * n, "Low": [9.0] * n, "Close": [10.0] * n})
    assert atr(df).iloc[-1] == pytest.approx(2.0)


def test_bollinger_flat_series_has_zero_width():
    upper, mid, lower = bollinger(pd.Series([5.0] * 30))
    assert upper.iloc[-1] == lower.iloc[-1] == mid.iloc[-1] == 5.0


def test_trend_of():
    assert trend_of(10, 9, 8) == "alta"
    assert trend_of(7, 8, 9) == "baixa"
    assert trend_of(8.5, 9, 8) == "lateral"
    assert trend_of(10, float("nan"), 8) == "indefinida"


def test_snapshot_shape():
    idx = pd.date_range("2025-01-01", periods=300, freq="D", tz="UTC")
    close = 100 + np.random.default_rng(3).normal(0, 1, 300).cumsum()
    df = pd.DataFrame(
        {"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1000.0}, index=idx
    )
    s = snapshot(df)
    assert 0 <= s["rsi14"] <= 100
    assert s["trend"] in {"alta", "baixa", "lateral"}
    assert s["volume_ratio"] == pytest.approx(1.0)
    assert s["bars"] == 300
