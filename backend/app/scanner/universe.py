"""Universos varridos pelo scanner: S&P 500 + Nasdaq-100, cripto (top por volume na Binance) e forex."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from ..providers.binance import _get as binance_get

DATA = Path(__file__).parent / "data"

CRYPTO_TOP = 60
CRYPTO_MIN_VOLUME = 10_000_000  # US$ negociados em 24h

FOREX_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
FOREX_MINORS = [
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD", "CADJPY", "CADCHF", "CHFJPY",
]
FOREX_EXTRAS = ["XAUUSD"]  # ouro: no Yahoo vira o futuro GC=F (ver providers/symbols.py)

# Bases que não são "cripto negociável" para o scanner: stablecoins e moedas fiduciárias.
_NOT_CRYPTO_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "USDE", "USD1", "XUSD", "USDS", "BFUSD",
    "EUR", "AEUR", "EURI", "GBP", "TRY", "BRL", "AUD", "RUB", "UAH", "ARS", "PLN", "JPY",
}
_LEVERAGED_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")


def _read_csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def stock_names() -> dict[str, str]:
    """símbolo -> nome, união de S&P 500 e Nasdaq-100 (sem duplicatas)."""
    names: dict[str, str] = {}
    for fname in ("sp500.csv", "nasdaq100.csv"):
        for row in _read_csv(fname):
            names.setdefault(row["symbol"], row["name"])
    return names


def stock_symbols() -> list[str]:
    return sorted(stock_names())


def forex_symbols() -> list[str]:
    return [*FOREX_MAJORS, *FOREX_MINORS, *FOREX_EXTRAS]


def is_tradable_crypto(symbol: str) -> bool:
    if not symbol.endswith("USDT") or symbol.endswith(_LEVERAGED_SUFFIXES):
        return False
    base = symbol[:-4]
    return bool(base) and base not in _NOT_CRYPTO_BASES and not base.startswith("USD") and not base.endswith("USD")


def crypto_symbols(limit: int = CRYPTO_TOP, min_volume: float = CRYPTO_MIN_VOLUME) -> list[str]:
    """Pares USDT mais líquidos da Binance nas últimas 24h (sem stablecoins nem tokens alavancados)."""
    rows = binance_get("/api/v3/ticker/24hr", {})
    ranked = sorted(
        ((float(r["quoteVolume"]), r["symbol"]) for r in rows if is_tradable_crypto(r["symbol"])), reverse=True
    )
    return [sym for vol, sym in ranked if vol >= min_volume][:limit]


def symbols_for(market: str) -> list[str]:
    if market == "acoes":
        return stock_symbols()
    if market == "forex":
        return forex_symbols()
    if market == "cripto":
        return crypto_symbols()
    raise ValueError(f"Mercado inválido: {market!r}")
