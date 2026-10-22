"""Fonte Binance (API pública de mercado; não exige chave)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .base import COLUMNS, PriceHistory, ProviderError

BASES = ("https://api.binance.com", "https://data-api.binance.vision")
STEP_MS = {"1m": 60_000, "1h": 3_600_000, "1d": 86_400_000}
LIMIT = 1000


def _get(path: str, params: dict) -> list:
    last_err: Exception | None = None
    for base in BASES:
        url = f"{base}{path}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 400:  # símbolo inválido: outra base não adianta
                raise ProviderError(f"Binance não conhece o símbolo {params.get('symbol')}") from exc
            last_err = exc
        except Exception as exc:
            last_err = exc
    raise ProviderError(f"Binance indisponível: {last_err}")


class BinanceProvider:
    name = "binance"

    def history(self, market: str, symbol: str, interval: str, days: int) -> PriceHistory:
        if interval not in STEP_MS:
            raise ProviderError(f"Intervalo não suportado: {interval}")
        now_ms = int(time.time() * 1000)
        cursor = int(now_ms - days * 86_400_000)
        rows: list = []
        while cursor < now_ms:
            batch = _get(
                "/api/v3/klines",
                {"symbol": symbol, "interval": interval, "startTime": cursor, "limit": LIMIT},
            )
            if not batch:
                break
            rows.extend(batch)
            cursor = batch[-1][0] + STEP_MS[interval]
            if len(batch) < LIMIT:
                break
        if not rows:
            raise ProviderError(f"Binance sem dados para {symbol}")
        df = pd.DataFrame(rows).iloc[:, :6]
        df.columns = ["t", *COLUMNS]
        df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
        return PriceHistory(
            df=df.astype(float), source=self.name, symbol_at_source=symbol, interval=interval
        )
