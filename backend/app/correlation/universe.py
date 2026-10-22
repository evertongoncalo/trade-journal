"""Universo de candidatos a correlação, referências fixas e regras de relação mecânica.

Os símbolos são os do Yahoo Finance. A lista é um ponto de partida (~46 instrumentos) e deve ficar editável.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yfinance as yf


@dataclass(frozen=True)
class Instrument:
    symbol: str
    label: str
    group: str


G_RISK = "Risco e índices"
G_USD = "Dólar e juros"
G_COM = "Commodities"
G_CRYPTO = "Cripto"
G_FX = "Forex"
G_SECT = "Setores (EUA)"

DXY = "DX-Y.NYB"

_FX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDNZD", "AUDJPY", "EURCHF",
]

CANDIDATES: list[Instrument] = [
    Instrument("^GSPC", "S&P 500", G_RISK),
    Instrument("^NDX", "Nasdaq 100", G_RISK),
    Instrument("^RUT", "Russell 2000", G_RISK),
    Instrument("^GDAXI", "DAX", G_RISK),
    Instrument("^FTSE", "FTSE 100", G_RISK),
    Instrument("^N225", "Nikkei 225", G_RISK),
    Instrument("^HSI", "Hang Seng", G_RISK),
    Instrument("^VIX", "VIX", G_RISK),
    Instrument("HYG", "Crédito high yield (HYG)", G_RISK),
    Instrument(DXY, "DXY (dólar)", G_USD),
    Instrument("^TNX", "Juro 10 anos (EUA)", G_USD),
    Instrument("^FVX", "Juro 5 anos (EUA)", G_USD),
    Instrument("TLT", "Treasuries longos (TLT)", G_USD),
    Instrument("GC=F", "Ouro (futuro)", G_COM),
    Instrument("SI=F", "Prata (futuro)", G_COM),
    Instrument("CL=F", "Petróleo WTI (futuro)", G_COM),
    Instrument("HG=F", "Cobre (futuro)", G_COM),
    Instrument("NG=F", "Gás natural (futuro)", G_COM),
    Instrument("BTC-USD", "Bitcoin", G_CRYPTO),
    Instrument("ETH-USD", "Ethereum", G_CRYPTO),
    Instrument("SOL-USD", "Solana", G_CRYPTO),
    *[Instrument(f"{p}=X", p, G_FX) for p in _FX_PAIRS],
    Instrument("XLK", "Tecnologia (XLK)", G_SECT),
    Instrument("XLF", "Financeiro (XLF)", G_SECT),
    Instrument("XLE", "Energia (XLE)", G_SECT),
    Instrument("XLV", "Saúde (XLV)", G_SECT),
    Instrument("XLY", "Consumo cíclico (XLY)", G_SECT),
    Instrument("XLP", "Consumo defensivo (XLP)", G_SECT),
    Instrument("XLI", "Industriais (XLI)", G_SECT),
    Instrument("XLU", "Utilidades (XLU)", G_SECT),
    Instrument("SMH", "Semicondutores (SMH)", G_SECT),
]

# Referências sempre visíveis no painel (ordem importa: a primeira alimenta o gráfico de dispersão).
FIXED: list[tuple[str, str]] = [("^GSPC", "S&P 500"), (DXY, "DXY")]

# Juros entram como variação em pontos, não em %.
YIELD_SYMBOLS = {"^TNX", "^FVX"}

_SECTOR_ETFS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Utilities": "XLU",
}


def fx_currencies(symbol: str) -> set[str]:
    """{'EUR','USD'} para 'EURUSD=X'; vazio para o resto."""
    if symbol.endswith("=X") and len(symbol) == 8:
        s = symbol[:-2]
        return {s[:3], s[3:]}
    return set()


def is_mechanical(target: str, other: str, own_sector_etfs: frozenset[str] = frozenset()) -> bool:
    """Relações que existem por construção e não trazem informação:

    - dois pares de forex com moeda em comum;
    - DXY contra par que tem USD (o dólar compõe o índice);
    - ação contra o ETF do próprio setor.
    """
    ct, co = fx_currencies(target), fx_currencies(other)
    if ct and co and (ct & co):
        return True
    if DXY in (target, other):
        counterpart = other if target == DXY else target
        if "USD" in fx_currencies(counterpart):
            return True
    return other in own_sector_etfs


@lru_cache(maxsize=256)
def own_sector_etfs(yahoo_symbol: str) -> frozenset[str]:
    """ETFs de setor que contêm a ação (para marcá-los como mecânicos). Falha em silêncio: devolve vazio."""
    try:
        info = yf.Ticker(yahoo_symbol).info
    except Exception:
        return frozenset()
    out: set[str] = set()
    etf = _SECTOR_ETFS.get(info.get("sector") or "")
    if etf:
        out.add(etf)
    if "Semiconductor" in (info.get("industry") or ""):
        out.add("SMH")
    return frozenset(out)
