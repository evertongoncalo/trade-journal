"""Escolha da fonte por mercado, com cache curto e reserva (cripto cai para o Yahoo se a Binance falhar)."""
from __future__ import annotations

import time

from .base import PriceHistory, ProviderError
from .binance import BinanceProvider
from .yahoo import YahooProvider

_yahoo = YahooProvider()
_binance = BinanceProvider()

_TTL_SECONDS = {"1h": 60, "1d": 300}
_cache: dict[tuple, tuple[float, PriceHistory]] = {}


def _fetch_uncached(market: str, symbol: str, interval: str, days: int) -> PriceHistory:
    if market == "cripto":
        try:
            return _binance.history(market, symbol, interval, days)
        except ProviderError as exc:
            hist = _yahoo.history(market, symbol, interval, days)
            hist.note = f"Binance falhou ({exc}); usando Yahoo. {hist.note}".strip()
            return hist
    return _yahoo.history(market, symbol, interval, days)


def fetch(market: str, symbol: str, interval: str, days: int) -> PriceHistory:
    key = (market, symbol, interval, days)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_SECONDS.get(interval, 60):
        return hit[1]
    hist = _fetch_uncached(market, symbol, interval, days)
    _cache[key] = (time.monotonic(), hist)
    return hist
