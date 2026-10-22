"""Preços recentes para a vigilância: a granularidade acompanha o tempo que o app ficou sem olhar."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ..providers import registry


def pick_interval(span: timedelta) -> str:
    """Janela curta -> barras de 1 minuto; se o app ficou desligado por mais tempo, barras maiores (o que
    cobre o intervalo todo, com menos precisão do instante do toque)."""
    if span <= timedelta(hours=36):
        return "1m"
    if span <= timedelta(days=25):
        return "1h"
    return "1d"


def fetch_window(market: str, symbol: str, since: datetime, now: datetime) -> tuple[pd.DataFrame, str]:
    """Barras (índice UTC; colunas Open/High/Low/Close/Volume) desde `since`, e o intervalo usado."""
    span = max(now - since, timedelta(0))
    interval = pick_interval(span)
    days = span.total_seconds() / 86400 + 0.25  # folga para não perder a barra da borda
    hist = registry.fetch_fresh(market, symbol, interval, days)
    return hist.df, interval
