import numpy as np
import pandas as pd
import pytest

from app.scanner import conditions as c


def frame(**cols):
    """Quadro de features com os valores dados (último valor = barra atual, penúltimo = barra anterior)."""
    n = max(len(v) for v in cols.values())
    return pd.DataFrame({k: list(v) if len(v) == n else [np.nan] * (n - len(v)) + list(v) for k, v in cols.items()})


def ok(cond_id, d, **p):
    spec = c.CATALOG[cond_id]
    params = {pp.name: pp.default for pp in spec.params} | p
    return spec.fn(d, params)


def test_rsi_between():
    assert ok("rsi_between", frame(rsi14=[55]), lo=40, hi=60) is True
    assert ok("rsi_between", frame(rsi14=[61]), lo=40, hi=60) is False
    assert ok("rsi_between", frame(rsi14=[np.nan]), lo=40, hi=60) is None


def test_rsi_crosses_use_previous_bar():
    assert ok("rsi_cross_up", frame(rsi14=[28, 31]), level=30) is True
    assert ok("rsi_cross_up", frame(rsi14=[30, 31]), level=30) is True  # ontem exatamente no nível
    assert ok("rsi_cross_up", frame(rsi14=[31, 33]), level=30) is False  # já estava acima
    assert ok("rsi_cross_up", frame(rsi14=[np.nan, 33]), level=30) is None
    assert ok("rsi_cross_down", frame(rsi14=[72, 68]), level=70) is True
    assert ok("rsi_cross_down", frame(rsi14=[68, 66]), level=70) is False


def test_rsi_direction():
    assert ok("rsi_rising", frame(rsi14=[50, 52])) is True
    assert ok("rsi_rising", frame(rsi14=[52, 50])) is False
    assert ok("rsi_falling", frame(rsi14=[52, 50])) is True


def test_macd_conditions():
    above = frame(macd=[1, 2], macd_signal=[1.5, 1.0], macd_hist=[-0.5, 1.0])
    assert ok("macd_above_signal", above) is True
    assert ok("macd_below_signal", above) is False
    assert ok("macd_cross_up", above) is True  # ontem abaixo, hoje acima
    assert ok("macd_cross_down", above) is False
    assert ok("macd_hist_rising", above) is True
    below = frame(macd=[2, 1], macd_signal=[1.0, 1.5], macd_hist=[1.0, -0.5])
    assert ok("macd_cross_down", below) is True
    assert ok("macd_hist_rising", below) is False
    assert ok("macd_cross_up", frame(macd=[2.0], macd_signal=[1.0])) is None  # sem barra anterior


def test_trend_conditions():
    assert ok("trend_up", frame(Close=[10], sma20=[9], sma50=[8])) is True
    assert ok("trend_up", frame(Close=[10], sma20=[9], sma50=[9.5])) is False
    assert ok("trend_down", frame(Close=[7], sma20=[8], sma50=[9])) is True
    assert ok("trend_up", frame(Close=[10], sma20=[np.nan], sma50=[8])) is None


def test_close_vs_sma_uses_the_period_asked():
    d = frame(Close=[1, 2, 3, 4, 10])
    assert ok("close_above_sma", d, n=3) is True  # média dos 3 últimos = 5,67
    assert ok("close_below_sma", d, n=3) is False
    assert ok("close_above_sma", d, n=50) is None  # histórico curto


def test_volume_bollinger_and_atr():
    assert ok("volume_ratio_above", frame(vol_ratio=[1.5]), x=1.2) is True
    assert ok("volume_ratio_above", frame(vol_ratio=[1.0]), x=1.2) is False
    assert ok("volume_ratio_above", frame(vol_ratio=[np.nan]), x=1.2) is None
    assert ok("bb_pctb_between", frame(bb_pctb=[0.2]), lo=0, hi=0.5) is True
    assert ok("atr_pct_between", frame(atr_pct=[8.0]), lo=0.5, hi=6) is False


def test_near_high_and_pullback_from_high():
    d = frame(Close=[100, 98, 95], High=[100, 101, 99])
    # máxima = 101: 95 < 101 × 0,95 = 95,95 (fora de 5%), mas 95 ≥ 101 × 0,94 = 94,94 (dentro de 6%)
    assert ok("near_high", d, lookback=3, within_pct=6) is True
    assert ok("near_high", d, lookback=3, within_pct=5) is False
    assert ok("pullback_from_high", d, lookback=3, min_pct=3, max_pct=10) is True  # recuo de 5,94%
    assert ok("pullback_from_high", d, lookback=3, min_pct=7, max_pct=10) is False
    assert ok("near_high", d, lookback=252, within_pct=5) is None


def test_up_and_down_day():
    assert ok("up_day", frame(Close=[10, 11])) is True
    assert ok("down_day", frame(Close=[10, 11])) is False


def test_render_labels():
    assert c.CATALOG["rsi_between"].render({"lo": 40.0, "hi": 60.0}) == "RSI(14) entre 40 e 60"
    assert c.CATALOG["volume_ratio_above"].render({"x": 1.2}) == "Volume > 1.2× a média de 20 barras"
    assert c.CATALOG["trend_up"].render({}) == "Tendência de alta (preço > MM20 > MM50)"


def test_normalize_condition_fills_defaults_and_validates():
    assert c.normalize_condition({"type": "rsi_between"}) == {"type": "rsi_between", "params": {"lo": 40.0, "hi": 60.0}}
    assert c.normalize_condition({"type": "rsi_between", "params": {"lo": 30}})["params"] == {"lo": 30.0, "hi": 60.0}
    with pytest.raises(ValueError, match="desconhecida"):
        c.normalize_condition({"type": "nao_existe"})
    with pytest.raises(ValueError, match="intervalo"):
        c.normalize_condition({"type": "rsi_between", "params": {"lo": -5}})
    with pytest.raises(ValueError, match="numérico"):
        c.normalize_condition({"type": "rsi_between", "params": {"lo": "abc"}})


def test_normalize_definition_rules():
    base = {"required": [{"type": "trend_up"}], "confirmations": [{"type": "up_day"}], "min_confirmations": 1}
    out = c.normalize_definition(base)
    assert out["filters"] == {"min_price": 0.0, "min_dollar_volume": 0.0}
    with pytest.raises(ValueError, match="pelo menos uma condição"):
        c.normalize_definition({})
    with pytest.raises(ValueError, match="min_confirmations"):
        c.normalize_definition({**base, "min_confirmations": 2})
    with pytest.raises(ValueError, match="pelo menos 1 confirmação"):
        c.normalize_definition({"confirmations": [{"type": "up_day"}], "min_confirmations": 0})


def test_catalog_is_consistent():
    ids = [x.id for x in c.CONDITIONS]
    assert len(ids) == len(set(ids))
    payload = c.catalog_payload()
    assert {p["id"] for p in payload} == set(ids)
    for spec in c.CONDITIONS:  # cada condição roda com os parâmetros padrão sem quebrar
        d = frame(
            Close=[10, 11], High=[11, 12], rsi14=[50, 55], macd=[1, 2], macd_signal=[1, 1], macd_hist=[0, 1],
            sma20=[9, 9], sma50=[8, 8], vol_ratio=[1, 1], bb_pctb=[0.5, 0.5], atr_pct=[2, 2],
        )
        assert spec.fn(d, {p.name: p.default for p in spec.params}) in (True, False, None)
