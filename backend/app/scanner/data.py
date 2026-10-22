"""Download do histórico diário do universo inteiro, só com barras já fechadas.

Os ativos que falham são devolvidos em `errors` e aparecem no resultado da varredura (o scanner antigo
engolia esses erros em silêncio).
"""
from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

import pandas as pd
import yfinance as yf

from ..providers.base import COLUMNS, ProviderError
from ..providers.binance import _get as binance_get
from ..providers.symbols import yahoo_symbol

NY = "America/New_York"
BATCH = 40
MIN_BARS = 60
Progress = Callable[[int], None]  # recebe quantos ativos acabaram de ser processados


def last_close_cutoff(now: datetime | None = None) -> pd.Timestamp:
    """Último 16:00 de Nova York já passado (em UTC). Barras que começam depois dele ainda estão em formação."""
    ny = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert(NY)
    cutoff = ny.replace(hour=16, minute=0, second=0, microsecond=0)
    if ny < cutoff:
        cutoff -= pd.Timedelta(days=1)
    return cutoff.tz_convert("UTC")


def _to_utc(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Datas sem fuso (barras diárias) viram a meia-noite de Nova York; com fuso, convertem para UTC."""
    idx = pd.DatetimeIndex(idx)
    return idx.tz_localize(NY).tz_convert("UTC") if idx.tz is None else idx.tz_convert("UTC")


def _clean(d: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame | None:
    d = d[COLUMNS].dropna(subset=["Close"])
    d.index = _to_utc(d.index)
    d = d[d.index <= cutoff]
    return d if len(d) >= MIN_BARS else None


def fetch_yahoo_daily(
    pairs: list[tuple[str, str]], cutoff: pd.Timestamp, progress: Progress | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """pairs = [(símbolo de exibição, símbolo no Yahoo)]. Devolve (quadros por símbolo de exibição, erros)."""
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for i in range(0, len(pairs), BATCH):
        batch = pairs[i : i + BATCH]
        ysyms = [y for _, y in batch]
        raw = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = yf.download(
                    ysyms, period="2y", interval="1d", progress=False, auto_adjust=True,
                    group_by="ticker", threads=True,
                )
        except Exception:
            raw = None
        for shown, ysym in batch:
            d = None
            if raw is not None and not raw.empty:
                try:
                    d = raw[ysym] if isinstance(raw.columns, pd.MultiIndex) else raw
                    d = _clean(d, cutoff)
                except KeyError:
                    d = None
            if d is None:  # tenta de novo sozinho antes de desistir
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        d = _clean(yf.Ticker(ysym).history(period="2y", interval="1d", auto_adjust=True), cutoff)
                except Exception:
                    d = None
            if d is None:
                errors[shown] = "sem dados suficientes no Yahoo"
            else:
                frames[shown] = d
        if progress:
            progress(len(batch))
    return frames, errors


def _binance_one(symbol: str, now_ms: int) -> pd.DataFrame:
    rows = binance_get("/api/v3/klines", {"symbol": symbol, "interval": "1d", "limit": 400})
    if not rows:
        raise ProviderError("sem dados")
    df = pd.DataFrame(rows).iloc[:, :7]
    df.columns = ["t", *COLUMNS, "close_time"]
    df = df[df["close_time"].astype("int64") <= now_ms]  # descarta o dia UTC ainda em andamento
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df = df.drop(columns="close_time").astype(float)
    if len(df) < MIN_BARS:
        raise ProviderError("histórico curto")
    return df


def fetch_binance_daily(
    symbols: list[str], progress: Progress | None = None, workers: int = 8
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    now_ms = int(time.time() * 1000)
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}

    def one(sym: str):
        try:
            return sym, _binance_one(sym, now_ms), None
        except Exception as exc:
            return sym, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for sym, df, err in pool.map(one, symbols):
            if df is not None:
                frames[sym] = df
            else:
                errors[sym] = err or "falhou"
            if progress:
                progress(1)
    return frames, errors


def fetch_daily(
    market: str, symbols: list[str], progress: Progress | None = None, now: datetime | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    if market == "cripto":
        return fetch_binance_daily(symbols, progress)
    pairs = [(s, yahoo_symbol(market, s)[0]) for s in symbols]
    return fetch_yahoo_daily(pairs, last_close_cutoff(now), progress)
