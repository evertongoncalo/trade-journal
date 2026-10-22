"""Avaliação dos setups sobre o histórico (diário ou H4) de cada ativo."""
from __future__ import annotations

import pandas as pd

from ..analysis.indicators import add_indicators, trend_of
from .bars import NY, block_end
from .conditions import CATALOG

MIN_BARS = 60  # histórico mínimo para avaliar (as médias de 50 dias precisam existir)


def features(df: pd.DataFrame, slot_tz: str | None = None) -> pd.DataFrame:
    """Indicadores + colunas derivadas usadas pelas condições.

    `slot_tz` (só H4): o volume de uma barra é comparado com as barras do MESMO horário do dia nesse fuso. Sem isso, a barra
    da manhã de uma ação (mais volume) sempre pareceria "acima da média" e a da tarde sempre "abaixo".
    """
    d = add_indicators(df)
    d["atr_pct"] = d["atr14"] / d["Close"] * 100
    width = d["bb_upper"] - d["bb_lower"]
    d["bb_pctb"] = (d["Close"] - d["bb_lower"]) / width.where(width > 0)
    vol = d["Volume"]
    if vol.sum() <= 0:
        d["vol_ratio"] = float("nan")
    elif slot_tz:
        local = df.index.tz_convert(slot_tz)
        slot = local.hour * 60 + local.minute
        d["vol_ratio"] = vol / vol.groupby(slot).transform(lambda x: x.rolling(20).mean())
    else:
        d["vol_ratio"] = vol / vol.rolling(20).mean()
    return d


def has_volume(df: pd.DataFrame) -> bool:
    return bool(df["Volume"].tail(20).sum() > 0)


def dollar_volume_per_day(d: pd.DataFrame, timeframe: str = "D1") -> float:
    """Volume financeiro médio por DIA nos últimos 20 pregões, em qualquer timeframe (o filtro é sempre por dia)."""
    dv = d["Close"] * d["Volume"]
    if timeframe != "H4":
        return float(dv.tail(20).mean())
    per_day = dv.groupby(d.index.tz_convert(NY).date).sum()
    last = d.index[-1].tz_convert(NY)
    if last.hour * 60 + last.minute < 13 * 60 + 30 and len(per_day) > 1:  # hoje só tem a barra da manhã: dia incompleto
        per_day = per_day.iloc[:-1]
    return float(per_day.tail(20).mean())


def passes_filters(d: pd.DataFrame, market: str, filters: dict, timeframe: str = "D1") -> bool:
    """Filtros de liquidez: valem só para ações (cripto já vem filtrada por volume; forex não tem volume)."""
    if market != "acoes":
        return True
    if float(d["Close"].iloc[-1]) < filters.get("min_price", 0):
        return False
    min_dv = filters.get("min_dollar_volume", 0)
    if min_dv:
        if not dollar_volume_per_day(d, timeframe) >= min_dv:
            return False
    return True


def evaluate_setup(defn: dict, d: pd.DataFrame, volume_ok: bool, timeframe: str = "D1") -> dict | None:
    """Devolve as condições que bateram, ou None se o ativo não atende o setup.

    - Obrigatórias: todas precisam ser verdadeiras (dado faltando reprova; condição de volume sem volume é ignorada).
    - Confirmações: pelo menos `min_confirmations` entre as aplicáveis.
    """
    required, not_applicable = [], []
    for c in defn["required"]:
        spec = CATALOG[c["type"]]
        label = spec.render(c["params"], timeframe)
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
        label = spec.render(c["params"], timeframe)
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


def evaluate_symbol(
    market: str, symbol: str, df: pd.DataFrame, setups: list[dict], timeframe: str = "D1"
) -> list[dict]:
    """Avalia os setups habilitados (do mercado e do timeframe do `df`) sobre um ativo e devolve os acertos."""
    if len(df) < MIN_BARS:
        return []
    d = features(df, ("UTC" if market == "cripto" else NY) if timeframe == "H4" else None)
    volume_ok = has_volume(df)
    last = d.iloc[-1]
    if timeframe == "H4":  # barra H4: início e fim em UTC (a tela mostra no fuso da grade do mercado)
        as_of, as_of_end = d.index[-1].isoformat(), block_end(market, d.index[-1]).isoformat()
    else:
        as_of, as_of_end = d.index[-1].date().isoformat(), None
    snapshot = {
        "price": float(last["Close"]),
        "timeframe": timeframe,
        "as_of": as_of,
        "as_of_end": as_of_end,
        "rsi14": _f(last["rsi14"]),
        "macd_hist": _f(last["macd_hist"]),
        "trend": trend_of(last["Close"], last["sma20"], last["sma50"]),
        "atr_pct": _f(last["atr_pct"]),
        "volume_ratio": _f(last["vol_ratio"]) if volume_ok else None,
        "bb_pctb": _f(last["bb_pctb"]),
    }
    hits = []
    for s in setups:
        if s.get("timeframe", "D1") != timeframe or market not in s["markets"]:
            continue
        if not passes_filters(d, market, s["definition"]["filters"], timeframe):
            continue
        result = evaluate_setup(s["definition"], d, volume_ok, timeframe)
        if result is not None:
            hits.append(
                {
                    "setup_id": s["id"], "setup_name": s["name"], "direction": s["direction"],
                    "market": market, "symbol": symbol, "price": snapshot["price"], "timeframe": timeframe,
                    "details": {**snapshot, **result},
                }
            )
    return hits


def _f(x) -> float | None:
    return None if pd.isna(x) else float(x)
