"""Normalização de símbolos por mercado e conversão para cada fonte e para o TradingView."""
from __future__ import annotations

import re

MARKETS = ("acoes", "cripto", "forex")

# O Yahoo não tem metais spot (XAUUSD=X não existe); usa-se o futuro como substituto.
YAHOO_FOREX_SUBSTITUTES = {
    "XAUUSD": ("GC=F", "Ouro spot não existe no Yahoo; usando o futuro GC=F como substituto."),
    "XAGUSD": ("SI=F", "Prata spot não existe no Yahoo; usando o futuro SI=F como substituto."),
}

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB")
_USD_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")

# Código de bolsa do Yahoo -> prefixo do TradingView
_TV_EXCHANGE = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "PCX": "AMEX",
    "ASE": "AMEX",
    "BTS": "BATS",
}


class SymbolError(ValueError):
    """Mercado ou símbolo inválido."""


def normalize(market: str, symbol: str) -> str:
    if market not in MARKETS:
        raise SymbolError(f"Mercado inválido: {market!r}")
    s = symbol.strip().upper().replace("/", "").replace(" ", "")
    if not s or not re.fullmatch(r"[A-Z0-9.\-=^]{1,20}", s):
        raise SymbolError(f"Símbolo inválido: {symbol!r}")
    if market == "forex" and not re.fullmatch(r"[A-Z]{6}", s):
        raise SymbolError("Forex usa 6 letras, ex.: EURUSD")
    if market == "cripto" and not any(s.endswith(q) and len(s) > len(q) for q in _QUOTES):
        s += "USDT"  # BTC -> BTCUSDT
    return s


def yahoo_symbol(market: str, symbol: str) -> tuple[str, str]:
    """(símbolo no Yahoo, nota explicando substituições)."""
    if market == "forex":
        if symbol in YAHOO_FOREX_SUBSTITUTES:
            return YAHOO_FOREX_SUBSTITUTES[symbol]
        return f"{symbol}=X", ""
    if market == "cripto":
        for q in _USD_QUOTES:
            if symbol.endswith(q):
                return f"{symbol[: -len(q)]}-USD", "Cripto no Yahoo cota em USD, não em USDT."
        for q in ("BTC", "ETH", "BNB"):
            if symbol.endswith(q) and len(symbol) > len(q):
                return f"{symbol[: -len(q)]}-{q}", ""
        return symbol, ""
    return symbol.replace(".", "-"), ""  # BRK.B -> BRK-B


def tradingview_symbol(market: str, symbol: str, yahoo_exchange: str | None = None) -> str:
    if market == "cripto":
        return f"BINANCE:{symbol}"
    if market == "forex":
        return f"OANDA:{symbol}"
    ticker = symbol.replace("-", ".")
    prefix = _TV_EXCHANGE.get(yahoo_exchange or "")
    return f"{prefix}:{ticker}" if prefix else ticker
