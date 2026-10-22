"""Indicadores técnicos. RSI e ATR usam a média de Wilder (a mesma do TradingView)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Média de Wilder: semente = média simples dos n primeiros valores válidos."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    first = valid[0]
    seed = first + n - 1
    out[seed] = v[first : seed + 1].mean()
    for i in range(seed + 1, len(v)):
        out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return pd.Series(out, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    avg_gain = rma(delta.clip(lower=0), n)
    avg_loss = rma((-delta).clip(lower=0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + avg_gain / avg_loss)
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["Close"].shift()
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return rma(tr, n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    return mid + k * sd, mid, mid - k * sd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["rsi14"] = rsi(out["Close"])
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(out["Close"])
    out["sma20"] = sma(out["Close"], 20)
    out["sma50"] = sma(out["Close"], 50)
    out["sma200"] = sma(out["Close"], 200)
    out["atr14"] = atr(out)
    out["bb_upper"], _, out["bb_lower"] = bollinger(out["Close"])
    return out


def trend_of(close: float, sma20: float, sma50: float) -> str:
    if any(pd.isna(x) for x in (close, sma20, sma50)):
        return "indefinida"
    if close > sma20 > sma50:
        return "alta"
    if close < sma20 < sma50:
        return "baixa"
    return "lateral"


def _f(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def snapshot(df: pd.DataFrame) -> dict:
    """Valores atuais dos indicadores (última barra)."""
    d = add_indicators(df)
    last = d.iloc[-1]
    close = float(last["Close"])
    width = last["bb_upper"] - last["bb_lower"]
    pctb = None if pd.isna(width) or width == 0 else float((close - last["bb_lower"]) / width)
    vol_ma = d["Volume"].rolling(20).mean().iloc[-1]
    has_volume = d["Volume"].sum() > 0 and not pd.isna(vol_ma) and vol_ma > 0
    return {
        "close": close,
        "rsi14": _f(last["rsi14"]),
        "macd": _f(last["macd"]),
        "macd_signal": _f(last["macd_signal"]),
        "macd_hist": _f(last["macd_hist"]),
        "sma20": _f(last["sma20"]),
        "sma50": _f(last["sma50"]),
        "sma200": _f(last["sma200"]),
        "atr14": _f(last["atr14"]),
        "atr_pct": None if pd.isna(last["atr14"]) else float(last["atr14"] / close * 100),
        "bb_upper": _f(last["bb_upper"]),
        "bb_lower": _f(last["bb_lower"]),
        "bb_pctb": pctb,
        "trend": trend_of(close, last["sma20"], last["sma50"]),
        "volume_ratio": float(last["Volume"] / vol_ma) if has_volume else None,
        "bars": len(d),
    }
