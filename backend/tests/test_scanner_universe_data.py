from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.providers.base import ProviderError
from app.scanner import data, universe


def ny(ts: str) -> datetime:
    return pd.Timestamp(ts, tz="America/New_York").tz_convert("UTC").to_pydatetime()


# ---------- universo ----------


def test_stock_universe_is_the_union_without_duplicates():
    syms = universe.stock_symbols()
    assert len(syms) == len(set(syms)) >= 500
    assert {"AAPL", "NVDA", "MSFT", "BRK-B"} <= set(syms)  # ponto vira hífen, como no Yahoo
    assert universe.stock_names()["AAPL"].startswith("Apple")


def test_forex_universe():
    fx = universe.forex_symbols()
    assert len(fx) == len(set(fx)) == 29 and "XAUUSD" in fx and "EURUSD" in fx and "GBPJPY" in fx


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", True), ("SOLUSDT", True), ("USDCUSDT", False), ("FDUSDUSDT", False),
        ("RLUSDUSDT", False), ("EURUSDT", False), ("BTCUPUSDT", False), ("ETHDOWNUSDT", False),
        ("BTCBUSD", False), ("USD1USDT", False),
    ],
)
def test_is_tradable_crypto(symbol, expected):
    assert universe.is_tradable_crypto(symbol) is expected


def test_crypto_symbols_ranks_by_volume_and_applies_threshold(monkeypatch):
    rows = [
        {"symbol": "BTCUSDT", "quoteVolume": "900000000"},
        {"symbol": "ETHUSDT", "quoteVolume": "500000000"},
        {"symbol": "USDCUSDT", "quoteVolume": "800000000"},  # stablecoin
        {"symbol": "DOGEUSDT", "quoteVolume": "20000000"},
        {"symbol": "TINYUSDT", "quoteVolume": "100000"},  # abaixo do mínimo
        {"symbol": "BNBBTC", "quoteVolume": "900000000"},  # não é USDT
    ]
    monkeypatch.setattr(universe, "binance_get", lambda path, params: rows)
    assert universe.crypto_symbols(limit=10, min_volume=1_000_000) == ["BTCUSDT", "ETHUSDT", "DOGEUSDT"]
    assert universe.crypto_symbols(limit=2, min_volume=1_000_000) == ["BTCUSDT", "ETHUSDT"]


def test_symbols_for_dispatch_and_validation(monkeypatch):
    monkeypatch.setattr(universe, "crypto_symbols", lambda: ["BTCUSDT"])
    assert universe.symbols_for("cripto") == ["BTCUSDT"]
    assert "XAUUSD" in universe.symbols_for("forex")
    with pytest.raises(ValueError):
        universe.symbols_for("bolsa")


# ---------- corte de barras incompletas ----------


def test_cutoff_is_the_last_16h_ny_that_already_passed():
    morning = data.last_close_cutoff(ny("2026-01-13 10:00"))
    evening = data.last_close_cutoff(ny("2026-01-13 17:00"))
    assert morning == pd.Timestamp(ny("2026-01-12 16:00"))
    assert evening == pd.Timestamp(ny("2026-01-13 16:00"))


def test_clean_drops_bars_that_start_after_the_cutoff_and_short_histories():
    idx = pd.date_range("2025-09-01", periods=80, freq="B")  # datas sem fuso
    df = pd.DataFrame({c: np.arange(80.0) + 1 for c in ["Open", "High", "Low", "Close", "Volume"]}, index=idx)
    cutoff = data.last_close_cutoff(ny("2026-01-13 10:00"))
    kept = data._clean(df, cutoff)
    assert kept is not None and kept.index.tz is not None
    assert kept.index[-1] <= cutoff
    in_progress = pd.DataFrame(df.iloc[:60].to_numpy(), columns=df.columns, index=pd.bdate_range("2025-11-03", periods=60))
    assert data._clean(in_progress, pd.Timestamp("2025-11-10", tz="UTC")) is None  # sobram menos de 60 barras


def test_binance_drops_the_day_still_in_progress(monkeypatch):
    now_ms = 1_800_000_000_000
    day = 86_400_000
    rows = []
    for k in range(70):
        open_t = now_ms - (70 - k) * day + 3_600_000  # a última barra abre 1h depois do limite e termina no futuro
        rows.append([open_t, "1", "2", "0.5", "1.5", "10", open_t + day - 1, "0", 0, "0", "0", "0"])
    monkeypatch.setattr(data, "binance_get", lambda path, params: rows)
    df = data._binance_one("BTCUSDT", now_ms)
    assert len(df) == 69 and df.index.tz is not None
    assert (df.index[-1].value // 1_000_000) + day - 1 <= now_ms


def test_binance_errors_are_reported(monkeypatch):
    monkeypatch.setattr(data, "binance_get", lambda path, params: [])
    with pytest.raises(ProviderError):
        data._binance_one("XXXUSDT", 1)

    calls = []

    def fake(sym, now_ms):
        calls.append(sym)
        if sym == "BAD":
            raise ProviderError("sem dados")
        idx = pd.date_range("2025-01-01", periods=70, freq="D", tz="UTC")
        return pd.DataFrame({c: 1.0 for c in ["Open", "High", "Low", "Close", "Volume"]}, index=idx)

    monkeypatch.setattr(data, "_binance_one", fake)
    done = []
    frames, errors = data.fetch_binance_daily(["OK", "BAD"], progress=done.append)
    assert list(frames) == ["OK"] and errors == {"BAD": "sem dados"} and sum(done) == 2


def test_fetch_daily_dispatches_by_market(monkeypatch):
    seen = {}
    monkeypatch.setattr(data, "fetch_binance_daily", lambda syms, progress=None: seen.setdefault("binance", syms) and ({}, {}))
    monkeypatch.setattr(
        data, "fetch_yahoo_daily", lambda pairs, cutoff, progress=None: seen.setdefault("yahoo", pairs) and ({}, {})
    )
    data.fetch_daily("cripto", ["BTCUSDT"])
    data.fetch_daily("forex", ["EURUSD", "XAUUSD"])
    data.fetch_daily("acoes", ["BRK-B"])
    assert seen["binance"] == ["BTCUSDT"]
    assert seen["yahoo"] == [("EURUSD", "EURUSD=X"), ("XAUUSD", "GC=F")]  # primeira chamada do Yahoo ficou guardada
