"""Barras de 4 horas (H4) montadas a partir de barras de 1 hora, só com barras já fechadas.

O Yahoo não entrega 4 horas; entrega 1 hora, que aqui é agrupada. A grade depende do mercado:
- cripto: a da Binance (00, 04, 08, 12, 16 e 20 UTC). Vem pronta da corretora e não passa por aqui.
- ações: duas barras por pregão, em Nova York: 09:30–13:30 e 13:30–16:00 (a segunda tem 2h30). É o mesmo corte do TradingView.
- forex e ouro: o dia do forex começa às 17:00 de Nova York; as barras começam às 17, 21, 01, 05, 09 e 13h (NY).
  O ouro (GC=F) fecha de 17:00 a 18:00 NY, então a barra das 17h tem só 3 horas de dados.
Cada barra recebe o horário em que ela COMEÇA (UTC), como no restante do app.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

NY = "America/New_York"
TIMEFRAMES = ("D1", "H4")

_HOUR = pd.Timedelta(hours=1)
_FOUR = pd.Timedelta(hours=4)
_STOCK_OPEN = pd.Timedelta(hours=9, minutes=30)
_STOCK_SPLIT = pd.Timedelta(hours=13, minutes=30)
_STOCK_CLOSE = pd.Timedelta(hours=16)
_FX_ANCHOR_HOUR = 17


def _blocks(index: pd.DatetimeIndex, market: str) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Início e fim (UTC) da barra H4 que contém cada barra de 1 hora (o índice é o início da hora, em UTC)."""
    local = index.tz_convert(NY)
    if market == "acoes":
        midnight = local.normalize().tz_convert("UTC")  # pregões nunca atravessam a troca de horário (domingo, 2h)
        first_half = (local.hour * 60 + local.minute) < 13 * 60 + 30
        start = (midnight + _STOCK_OPEN).where(first_half, midnight + _STOCK_SPLIT)
        end = (midnight + _STOCK_SPLIT).where(first_half, midnight + _STOCK_CLOSE)
        return start, end
    offset = pd.to_timedelta((local.hour - _FX_ANCHOR_HOUR) % 4, unit="h")
    start = index.floor("h") - offset
    return start, start + _FOUR


def block_end(market: str, start: pd.Timestamp) -> pd.Timestamp:
    """Quando termina a barra H4 que começa em `start` (UTC)."""
    start = pd.Timestamp(start)
    if market == "acoes":
        local = start.tz_convert(NY)
        if local.hour * 60 + local.minute >= 13 * 60 + 30:
            return (local.normalize() + _STOCK_CLOSE).tz_convert("UTC")
    return start + _FOUR


def h4_from_hourly(df: pd.DataFrame, market: str, now: datetime | None = None) -> pd.DataFrame:
    """Agrupa barras de 1 hora (índice UTC, rótulo = início) em barras H4 e descarta a última se ainda não fechou.

    A última barra só vale se o relógio já passou do fim dela E existe a barra de 1 hora que cobre o último trecho: o Yahoo
    publica ouro e índices com 10 a 15 minutos de atraso, e sem essa checagem uma barra nasceria sem a última hora.
    """
    if df.empty:
        return df
    df = df[~df.index.duplicated()].sort_index()
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    start, end = _blocks(df.index, market)
    grouped = df.groupby(start)
    out = pd.DataFrame(
        {
            "Open": grouped["Open"].first(),
            "High": grouped["High"].max(),
            "Low": grouped["Low"].min(),
            "Close": grouped["Close"].last(),
            "Volume": grouped["Volume"].sum(),
        }
    )
    out.index.name = None
    last_end = end[-1]
    if not (now_ts >= last_end and df.index[-1] >= last_end - _HOUR):
        out = out.iloc[:-1]
    return out
