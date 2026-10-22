"""Regra de disparo, pura: o nível foi tocado por alguma barra depois da criação do alerta?

Detecção pela máxima/mínima das barras (não só pelo último preço): um pavio que toca o nível entre duas
verificações também dispara. Alerta "acima" dispara quando a máxima >= nível; "abaixo", quando a mínima <= nível.

Só contam barras que começam depois da criação do alerta (a barra em andamento no momento da criação mistura
preços de antes), então o disparo pode atrasar até uma barra.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

INTERVAL_SECONDS = {"1m": 60, "1h": 3600, "1d": 86400}


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ceil_to(ts: datetime, interval: str) -> datetime:
    sec = INTERVAL_SECONDS[interval]
    return datetime.fromtimestamp(math.ceil(ts.timestamp() / sec) * sec, tz=timezone.utc)


def window_start(alert: dict, interval: str) -> datetime:
    """Primeira barra que ainda não foi verificada (ou a primeira depois da criação)."""
    if alert.get("checked_until"):
        return parse_ts(alert["checked_until"])
    return ceil_to(parse_ts(alert["created_at"]), interval)


def first_touch(alert: dict, bars: pd.DataFrame, interval: str) -> dict | None:
    """Primeira barra a tocar o nível: {'bar', 'extreme', 'close'} ou None."""
    window = bars[bars.index >= window_start(alert, interval)]
    if window.empty:
        return None
    if alert["direction"] == "acima":
        hit, col = window[window["High"] >= alert["price"]], "High"
    else:
        hit, col = window[window["Low"] <= alert["price"]], "Low"
    if hit.empty:
        return None
    row = hit.iloc[0]
    return {"bar": hit.index[0].to_pydatetime(), "extreme": float(row[col]), "close": float(row["Close"])}


def checked_until_after(alert: dict, bars: pd.DataFrame, interval: str) -> datetime | None:
    """Até onde a vigilância olhou: início da última barra da janela (ela é reavaliada no próximo ciclo,
    porque pode ainda estar em formação). None se não houve barra nova."""
    window = bars[bars.index >= window_start(alert, interval)]
    return None if window.empty else window.index[-1].to_pydatetime()
