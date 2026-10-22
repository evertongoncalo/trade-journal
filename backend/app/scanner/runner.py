"""Execução da varredura em segundo plano, com progresso."""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from . import data, engine, store, universe

MARKET_LABEL = {"acoes": "Ações", "cripto": "Cripto", "forex": "Forex"}

_lock = threading.Lock()
_status: dict = {
    "state": "idle", "phase": "", "done": 0, "total": 0,
    "started_at": None, "finished_at": None, "error": None, "run_id": None,
}


def status() -> dict:
    return dict(_status)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _most_common_date(frames: dict[str, pd.DataFrame]) -> str | None:
    dates = [df.index[-1].date().isoformat() for df in frames.values() if len(df)]
    return Counter(dates).most_common(1)[0][0] if dates else None


def run_scan(markets: list[str], now: datetime | None = None) -> int:
    """Varre os mercados pedidos (bloqueante) e grava o resultado. Normalmente roda em thread via start_run()."""
    setups = [s for s in store.list_setups() if s["enabled"] and set(s["markets"]) & set(markets)]
    run_id = store.create_run(markets, setups)
    _status["run_id"] = run_id
    total = ok = 0
    errors: dict[str, str] = {}
    as_of: dict[str, str | None] = {}
    try:
        _status.update(phase="Montando a lista de ativos", done=0, total=0)
        plan = {m: universe.symbols_for(m) for m in markets}
        total = sum(len(v) for v in plan.values())
        _status["total"] = total

        counter = [0]

        def progress(n: int) -> None:
            counter[0] += n
            _status["done"] = counter[0]

        hits: list[dict] = []
        for market in markets:
            _status["phase"] = f"Baixando e avaliando: {MARKET_LABEL[market]} ({len(plan[market])} ativos)"
            frames, errs = data.fetch_daily(market, plan[market], progress, now)
            errors.update({f"{market}:{sym}": reason for sym, reason in errs.items()})
            for sym, df in frames.items():
                ok += 1
                hits.extend(engine.evaluate_symbol(market, sym, df, setups))
            as_of[market] = _most_common_date(frames)

        store.save_hits(run_id, hits)
        store.finish_run(run_id, "done", total, ok, errors, as_of)
        _status.update(state="done", phase="", finished_at=_now())
    except Exception as exc:  # a thread não pode morrer em silêncio
        store.finish_run(run_id, "error", total, ok, errors, as_of, error=str(exc))
        _status.update(state="error", phase="", finished_at=_now(), error=str(exc))
    return run_id


def start_run(markets: list[str]) -> bool:
    """Inicia a varredura em segundo plano. Devolve False se já houver uma em andamento."""
    with _lock:
        if _status["state"] == "running":
            return False
        _status.update(
            state="running", phase="Iniciando", done=0, total=0, started_at=_now(), finished_at=None, error=None, run_id=None
        )
    threading.Thread(target=run_scan, args=(markets,), daemon=True).start()
    return True
