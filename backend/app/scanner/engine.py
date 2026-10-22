"""Avaliação dos setups sobre o histórico diário de cada ativo."""
from __future__ import annotations

import pandas as pd

from ..analysis.indicators import add_indicators, trend_of
from .conditions import CATALOG

MIN_BARS = 60  # histórico mínimo para avaliar (as médias de 50 dias precisam existir)


def features(df: pd.DataFrame) -> pd.DataFrame:
    """Indicadores + colunas derivadas usadas pelas condições."""
    d = add_indicators(df)
    d["atr_pct"] = d["atr14"] / d["Close"] * 100
    width = d["bb_upper"] - d["bb_lower"]
    d["bb_pctb"] = (d["Close"] - d["bb_lower"]) / width.where(width > 0)
    vol = d["Volume"]
    d["vol_ratio"] = vol / vol.rolling(20).mean() if vol.sum() > 0 else float("nan")
    return d


def has_volume(df: pd.DataFrame) -> bool:
    return bool(df["Volume"].tail(20).sum() > 0)


def passes_filters(d: pd.DataFrame, market: str, filters: dict) -> bool:
    """Filtros de liquidez: valem só para ações (cripto já vem filtrada por volume; forex não tem volume)."""
    if market != "acoes":
        return True
    if float(d["Close"].iloc[-1]) < filters.get("min_price", 0):
        return False
    min_dv = filters.get("min_dollar_volume", 0)
    if min_dv:
        dollar_volume = float((d["Close"] * d["Volume"]).tail(20).mean())
        if not dollar_volume >= min_dv:
            return False
    return True


def evaluate_setup(defn: dict, d: pd.DataFrame, volume_ok: bool) -> dict | None:
    """Devolve as condições que bateram, ou None se o ativo não atende o setup.

    - Obrigatórias: todas precisam ser verdadeiras (dado faltando reprova; condição de volume sem volume é ignorada).
    - Confirmações: pelo menos `min_confirmations` entre as aplicáveis.
    """
    required, not_applicable = [], []
    for c in defn["required"]:
        spec = CATALOG[c["type"]]
        label = spec.render(c["params"])
        if spec.needs_volume and not volume_ok:
            not_applicable.append(label)
            continue
        if spec.fn(d, c["params"]) is not True:
            return None
        required.append(label)

    met: list[str] = []
    applicable = 0
    for c in defn["confirmations"]:
        spec = CATALOG[c["type"]]
        label = spec.render(c["params"])
        if spec.needs_volume and not volume_ok:
            not_applicable.append(label)
            continue
        applicable += 1
        if spec.fn(d, c["params"]) is True:
            met.append(label)
    if len(met) < min(defn["min_confirmations"], applicable):
        return None
    return {
        "required": required,
        "confirmations": met,
        "confirmations_applicable": applicable,
        "not_applicable": not_applicable,
    }


def evaluate_symbol(market: str, symbol: str, df: pd.DataFrame, setups: list[dict]) -> list[dict]:
    """Avalia todos os setups habilitados (do mercado) sobre um ativo e devolve os acertos."""
    if len(df) < MIN_BARS:
        return []
    d = features(df)
    volume_ok = has_volume(df)
    last = d.iloc[-1]
    snapshot = {
        "price": float(last["Close"]),
        "as_of": d.index[-1].date().isoformat(),
        "rsi14": _f(last["rsi14"]),
        "macd_hist": _f(last["macd_hist"]),
        "trend": trend_of(last["Close"], last["sma20"], last["sma50"]),
        "atr_pct": _f(last["atr_pct"]),
        "volume_ratio": _f(last["vol_ratio"]) if volume_ok else None,
        "bb_pctb": _f(last["bb_pctb"]),
    }
    hits = []
    for s in setups:
        if market not in s["markets"] or not passes_filters(d, market, s["definition"]["filters"]):
            continue
        result = evaluate_setup(s["definition"], d, volume_ok)
        if result is not None:
            hits.append(
                {
                    "setup_id": s["id"], "setup_name": s["name"], "direction": s["direction"],
                    "market": market, "symbol": symbol, "price": snapshot["price"],
                    "details": {**snapshot, **result},
                }
            )
    return hits


def _f(x) -> float | None:
    return None if pd.isna(x) else float(x)
