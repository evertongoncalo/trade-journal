"""Contrato comum das fontes de preço."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class ProviderError(Exception):
    """Falha ao obter dados de uma fonte."""


@dataclass
class PriceHistory:
    df: pd.DataFrame  # índice UTC (tz-aware), colunas COLUMNS
    source: str  # "yahoo" | "binance"
    symbol_at_source: str
    interval: str  # "1d" | "1h"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""

    @property
    def last_bar(self) -> datetime | None:
        return None if self.df.empty else self.df.index[-1].to_pydatetime()

    def health(self) -> dict:
        """Saúde dos dados: fonte, última barra e idade dela (só faz sentido em intraday).

        Em 1h, idade <= 60 min significa que a última barra ainda está em formação.
        """
        last = self.last_bar
        age = None
        if last is not None and self.interval != "1d":
            age = round((self.fetched_at - last).total_seconds() / 60, 1)
        return {
            "source": self.source,
            "symbol_at_source": self.symbol_at_source,
            "interval": self.interval,
            "last_bar_utc": last.isoformat() if last else None,
            "last_bar_age_minutes": age,
            "note": self.note,
        }


class Provider(Protocol):
    name: str

    def history(self, market: str, symbol: str, interval: str, days: int) -> PriceHistory: ...
