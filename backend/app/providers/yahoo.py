"""Fonte Yahoo Finance (via yfinance). Não oficial: serve ao MVP e fica atrás da interface Provider."""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd
import yfinance as yf

from .base import COLUMNS, PriceHistory, ProviderError
from .symbols import yahoo_symbol

MAX_DAYS_1H = 725  # limite do Yahoo para dados de 1 hora
MAX_DAYS_1M = 6  # o Yahoo só guarda ~7 dias de dados de 1 minuto


class YahooProvider:
    name = "yahoo"

    def history(self, market: str, symbol: str, interval: str, days: int) -> PriceHistory:
        ysym, note = yahoo_symbol(market, symbol)
        if interval == "1h":
            days = min(days, MAX_DAYS_1H)
        elif interval == "1m":
            days = min(days, MAX_DAYS_1M)
        start = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = yf.Ticker(ysym).history(
                    start=start.strftime("%Y-%m-%d"), interval=interval, auto_adjust=True
                )
        except Exception as exc:  # o yfinance levanta vários tipos de erro
            raise ProviderError(f"Yahoo falhou para {ysym}: {exc}") from exc
        if df is None or df.empty:
            raise ProviderError(f"Yahoo sem dados para {ysym}")
        df = df[COLUMNS].dropna(subset=["Close"])
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        return PriceHistory(
            df=df, source=self.name, symbol_at_source=ysym, interval=interval, note=note
        )


@lru_cache(maxsize=512)
def exchange_of(yahoo_sym: str) -> str | None:
    """Código de bolsa do Yahoo (ex.: NMS, NYQ), usado para montar o símbolo do TradingView."""
    try:
        return yf.Ticker(yahoo_sym).fast_info["exchange"]
    except Exception:
        return None
