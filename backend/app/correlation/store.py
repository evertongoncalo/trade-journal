"""Séries diárias de fechamento alinhadas às 16:00 de Nova York (mesmo instante para todos os ativos).

Por quê: forex e cripto negociam 24h e os índices fecham em horários diferentes; com candles diários de cada
fonte, a correlação sai distorcida (EURUSD x DXY deu -0,10 no diário do Yahoo e -0,98 alinhado). Aqui cada
ativo é amostrado a partir de dados de 1 hora na última barra que fecha até 16:00 NY de cada dia.
Limite do Yahoo para 1 hora: ~730 dias, então a janela é de ~2 anos.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from .. import db
from .universe import CANDIDATES, FIXED

NY = "America/New_York"
HOURLY_DAYS = 720
BATCH = 12
STALE_HOURS = 20
MIN_HOURLY_BARS = 200


def snap_ny16(df: pd.DataFrame, now: datetime | None = None) -> pd.Series:
    """Fechamento de cada dia no instante 16:00 NY: último fechamento de barra de 1h que começa antes das 16h.

    Dias ainda não concluídos (antes das 16h NY de hoje) ficam de fora para todos os ativos.
    """
    close = df["Close"].dropna()
    idx = pd.DatetimeIndex(close.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    ny = pd.Series(close.to_numpy(), index=idx.tz_convert(NY))
    ny = ny[ny.index.hour < 16]
    out = ny.groupby(ny.index.date).last()
    out.index = pd.to_datetime(out.index)
    now_ny = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert(NY)
    last_done = now_ny.normalize().tz_localize(None) - (pd.Timedelta(0) if now_ny.hour >= 16 else pd.Timedelta(days=1))
    return out[out.index <= last_done]


# ---------- download ----------


def _from_batch(raw: pd.DataFrame, batch: list[str]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        top = set(raw.columns.get_level_values(0))
        frames = {t: raw[t] for t in batch if t in top}
    else:  # um único ativo: colunas simples
        frames = {batch[0]: raw}
    for t, d in frames.items():
        d = d.dropna(how="all")
        if len(d) >= MIN_HOURLY_BARS:
            out[t] = snap_ny16(d)
    return out


def download_snaps(symbols: list[str], progress=None) -> dict[str, pd.Series]:
    start = (datetime.now(timezone.utc) - timedelta(days=HOURLY_DAYS)).strftime("%Y-%m-%d")
    out: dict[str, pd.Series] = {}
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i : i + BATCH]
        try:
            raw = yf.download(
                batch, start=start, interval="1h", progress=False, auto_adjust=True,
                group_by="ticker", threads=True,
            )
            out.update(_from_batch(raw, batch))
        except Exception:
            pass
        for t in batch:  # o que faltou no lote tenta de novo, um a um
            if t in out:
                continue
            try:
                d = yf.Ticker(t).history(start=start, interval="1h", auto_adjust=True)
                out.update(_from_batch(d, [t]))
            except Exception:
                pass
        if progress:
            progress(min(i + BATCH, len(symbols)), len(symbols))
    return out


# ---------- SQLite ----------


def save_closes(symbol: str, series: pd.Series) -> None:
    rows = [(symbol, d.strftime("%Y-%m-%d"), float(v)) for d, v in series.dropna().items()]
    with db.connect() as con:
        con.execute("DELETE FROM closes_ny16 WHERE symbol = ?", (symbol,))
        con.executemany("INSERT INTO closes_ny16 (symbol, d, close) VALUES (?, ?, ?)", rows)
        con.execute(
            "INSERT OR REPLACE INTO closes_meta (symbol, updated_at, rows) VALUES (?, ?, ?)",
            (symbol, datetime.now(timezone.utc).isoformat(), len(rows)),
        )


def load_closes() -> pd.DataFrame:
    with db.connect() as con:
        rows = con.execute("SELECT symbol, d, close FROM closes_ny16").fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([tuple(r) for r in rows], columns=["symbol", "d", "close"])
    wide = df.pivot(index="d", columns="symbol", values="close").sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def load_meta() -> dict[str, datetime]:
    with db.connect() as con:
        rows = con.execute("SELECT symbol, updated_at FROM closes_meta").fetchall()
    return {r["symbol"]: datetime.fromisoformat(r["updated_at"]) for r in rows}


def expected_symbols() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in [i.symbol for i in CANDIDATES] + [s for s, _ in FIXED]:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def universe_state() -> dict:
    expected = expected_symbols()
    meta = load_meta()
    have = [s for s in expected if s in meta]
    missing = [s for s in expected if s not in meta]
    if not have:
        return {"state": "vazio", "symbols": 0, "expected": len(expected), "updated_at": None, "missing": missing}
    oldest = min(meta[s] for s in have)
    stale = datetime.now(timezone.utc) - oldest > timedelta(hours=STALE_HOURS)
    return {
        "state": "desatualizado" if stale else "ok",
        "symbols": len(have),
        "expected": len(expected),
        "updated_at": max(meta[s] for s in have).isoformat(),
        "missing": missing,
    }


# ---------- atualização em segundo plano ----------

_lock = threading.Lock()
_status: dict = {
    "state": "idle", "done": 0, "total": 0, "started_at": None, "finished_at": None, "error": None, "missing": [],
}


def status() -> dict:
    return dict(_status)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_universe(symbols: list[str] | None = None) -> None:
    """Baixa e grava o universo (bloqueante). Normalmente rodado em thread por start_refresh()."""
    symbols = symbols or expected_symbols()
    try:
        snaps = download_snaps(symbols, progress=lambda done, total: _status.update(done=done, total=total))
        for sym, series in snaps.items():
            save_closes(sym, series)
        _status.update(state="done", finished_at=_now(), missing=[s for s in symbols if s not in snaps])
    except Exception as exc:  # não derrubar a thread em silêncio
        _status.update(state="error", finished_at=_now(), error=str(exc))


def start_refresh(symbols: list[str] | None = None) -> bool:
    """Inicia a atualização em segundo plano. Devolve False se já houver uma em andamento."""
    symbols = symbols or expected_symbols()
    with _lock:
        if _status["state"] == "running":
            return False
        _status.update(
            state="running", done=0, total=len(symbols), started_at=_now(), finished_at=None, error=None, missing=[]
        )
    threading.Thread(target=refresh_universe, args=(symbols,), daemon=True).start()
    return True
