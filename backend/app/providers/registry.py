"""Escolha da fonte por mercado, com cache curto e reserva (cripto cai para o Yahoo se a Binance falhar)."""
from __future__ import annotations

import time

from .base import PriceHistory, ProviderError
from .binance import BinanceProvider
from .yahoo import YahooProvider

_yahoo = YahooProvider()
_binance = BinanceProvider()

_TTL_SECONDS = {"1m": 20, "1h": 60, "1d": 300}
_MAX_CACHE = 256
_cache: dict[tuple, tuple[float, PriceHistory]] = {}


def _fetch_uncached(market: str, symbol: str, interval: str, days: float) -> PriceHistory:
    if market == "cripto":
        try:
            return _binance.history(market, symbol, interval, days)
        except ProviderError as exc:
            hist = _yahoo.history(market, symbol, interval, days)
            hist.note = f"Binance falhou ({exc}); usando Yahoo. {hist.note}".strip()
            return hist
    return _yahoo.history(market, symbol, interval, days)


def fetch_fresh(market: str, symbol: str, interval: str, days: float) -> PriceHistory:
    """Busca sem cache: para quem pede uma janela diferente a cada chamada (vigilância dos alertas)."""
    return _fetch_uncached(market, symbol, interval, days)


def fetch(market: str, symbol: str, interval: str, days: int) -> PriceHistory:
    key = (market, symbol, interval, days)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL_SECONDS.get(interval, 60):
        return hit[1]
    hist = _fetch_uncached(market, symbol, interval, days)
    _cache[key] = (now, hist)
    if len(_cache) > _MAX_CACHE:  # descarta o que já venceu para o cache não crescer sem limite
        for k in [k for k, (t, _) in _cache.items() if now - t >= max(_TTL_SECONDS.values())]:
            _cache.pop(k, None)
    return hist
