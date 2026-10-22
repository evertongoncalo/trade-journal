"""Price action objetivo (só código): estrutura de topos e fundos, níveis próximos e as últimas barras.

Pivôs: um topo é a máxima mais alta numa janela de `k` barras para cada lado; um fundo, a mínima mais baixa.
O pivô só é confirmado depois de `k` barras, então os dois últimos candles nunca viram pivô.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr

PIVOT_K = 3
RECENT_BARS = 30


def _sig(x: float, digits: int = 6) -> float:
    return float(f"{x:.{digits}g}")


def pivots(df: pd.DataFrame, k: int = PIVOT_K) -> list[dict]:
    """Topos e fundos em ordem cronológica: [{'tipo', 'data', 'preco', 'i'}]."""
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    out = []
    for i in range(k, len(df) - k):
        win_h, win_l = high[i - k : i + k + 1], low[i - k : i + k + 1]
        if high[i] == win_h.max() and (win_h == high[i]).sum() == 1:
            out.append({"tipo": "topo", "data": df.index[i].date().isoformat(), "preco": _sig(high[i]), "i": i})
        if low[i] == win_l.min() and (win_l == low[i]).sum() == 1:
            out.append({"tipo": "fundo", "data": df.index[i].date().isoformat(), "preco": _sig(low[i]), "i": i})
    return out


def structure(points: list[dict]) -> str:
    """Compara os dois últimos topos e os dois últimos fundos."""
    tops = [p["preco"] for p in points if p["tipo"] == "topo"][-2:]
    bottoms = [p["preco"] for p in points if p["tipo"] == "fundo"][-2:]
    if len(tops) < 2 or len(bottoms) < 2:
        return "indefinida"
    up_t, up_b = tops[1] > tops[0], bottoms[1] > bottoms[0]
    if up_t and up_b:
        return "topos e fundos ascendentes"
    if not up_t and not up_b:
        return "topos e fundos descendentes"
    return "misto (topos e fundos em direções diferentes)"


def _pct(a: float, b: float) -> float | None:
    return None if b == 0 or pd.isna(a) or pd.isna(b) else round((a / b - 1) * 100, 2)


def summarize(df: pd.DataFrame) -> dict:
    """Resumo para a lente de price action. Exige histórico mínimo; devolve só o que pôde calcular."""
    close = float(df["Close"].iloc[-1])
    atr_now = atr(df).iloc[-1]
    points = pivots(df)
    recent = [p for p in points][-6:]

    def level(kind: str, above: bool) -> dict | None:
        prices = [p["preco"] for p in points[-12:] if p["tipo"] == kind and ((p["preco"] > close) if above else (p["preco"] < close))]
        if not prices:
            return None
        price = min(prices) if above else max(prices)  # o mais próximo do preço atual
        out = {"preco": price, "dist_pct": round((price / close - 1) * 100, 2)}
        if not pd.isna(atr_now) and atr_now > 0:
            out["dist_atr"] = round(abs(price - close) / float(atr_now), 2)
        return out

    def rng(n: int) -> tuple[float, float]:
        w = df.iloc[-n:]
        return float(w["High"].max()), float(w["Low"].min())

    hi20, lo20 = rng(20)
    hi252, lo252 = rng(min(252, len(df)))
    bars = df.iloc[-RECENT_BARS:]
    return {
        "ultimo_fechamento": _sig(close),
        "variacao_pct": {
            "5d": _pct(close, float(df["Close"].iloc[-6])) if len(df) > 5 else None,
            "20d": _pct(close, float(df["Close"].iloc[-21])) if len(df) > 20 else None,
            "60d": _pct(close, float(df["Close"].iloc[-61])) if len(df) > 60 else None,
        },
        "maxima_20d": _sig(hi20),
        "minima_20d": _sig(lo20),
        "maxima_52s": _sig(hi252),
        "minima_52s": _sig(lo252),
        "dist_maxima_52s_pct": _pct(close, hi252),
        "dist_minima_52s_pct": _pct(close, lo252),
        "posicao_no_range_52s": None if hi252 == lo252 else round((close - lo252) / (hi252 - lo252), 2),
        "estrutura": structure(points),
        "pivos_recentes": [{k: v for k, v in p.items() if k != "i"} for p in recent],
        "resistencia_proxima": level("topo", above=True),
        "suporte_proximo": level("fundo", above=False),
        "ultimas_barras": {
            "colunas": ["data", "abertura", "maxima", "minima", "fechamento"],
            "linhas": [
                [ix.date().isoformat(), _sig(o), _sig(h), _sig(l), _sig(c)]
                for ix, o, h, l, c in zip(bars.index, bars["Open"], bars["High"], bars["Low"], bars["Close"])
            ],
        },
    }
