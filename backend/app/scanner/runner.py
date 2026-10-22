"""Execução da varredura em segundo plano, com progresso."""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from . import data, engine, store, universe
from .bars import TIMEFRAMES

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


def _most_common_bar(frames: dict[str, pd.DataFrame], timeframe: str) -> str | None:
    """A barra mais comum entre os ativos: a data em D1; o início da barra (UTC, ISO) em H4."""
    stamp = (lambda ix: ix.date().isoformat()) if timeframe == "D1" else (lambda ix: ix.isoformat())
    bars = [stamp(df.index[-1]) for df in frames.values() if len(df)]
    return Counter(bars).most_common(1)[0][0] if bars else None


def run_scan(markets: list[str], now: datetime | None = None) -> int:
    """Varre os mercados pedidos (bloqueante) e grava o resultado. Normalmente roda em thread via start_run().

    Só baixa o que algum setup habilitado usa: um mercado sem setup não é baixado, e o histórico H4 só é baixado se
    houver setup H4 naquele mercado. Os erros de H4 levam o sufixo " (H4)" na chave.
    """
    setups = [s for s in store.list_setups() if s["enabled"] and set(s["markets"]) & set(markets)]
    run_id = store.create_run(markets, setups)
    _status["run_id"] = run_id
    total = ok = 0
    errors: dict[str, str] = {}
    as_of: dict[str, str | None] = {}
    try:
        _status.update(phase="Montando a lista de ativos", done=0, total=0)
        plan = {m: universe.symbols_for(m) for m in markets}
        needed = {
            m: [tf for tf in TIMEFRAMES if any(s["timeframe"] == tf and m in s["markets"] for s in setups)] for m in markets
        }
        total = sum(len(plan[m]) for m in markets if needed[m])
        _status["total"] = sum(len(plan[m]) * len(needed[m]) for m in markets)

        counter = [0]

        def progress(n: int) -> None:
            counter[0] += n
            _status["done"] = counter[0]

        hits: list[dict] = []
        for market in markets:
            ok_sets: list[set[str]] = []
            for tf in needed[market]:
                where = MARKET_LABEL[market] + ("" if tf == "D1" else f" · {tf}")
                _status["phase"] = f"Baixando e avaliando: {where} ({len(plan[market])} ativos)"
                frames, errs = data.fetch(market, tf, plan[market], progress, now)
                suffix = "" if tf == "D1" else f" ({tf})"
                errors.update({f"{market}:{sym}{suffix}": reason for sym, reason in errs.items()})
                for sym, df in frames.items():
                    hits.extend(engine.evaluate_symbol(market, sym, df, setups, tf))
                as_of[market if tf == "D1" else f"{market}:{tf}"] = _most_common_bar(frames, tf)
                ok_sets.append(set(frames))
            if ok_sets:
                ok += len(set.intersection(*ok_sets))  # ativo "avaliado" = todos os timeframes usados deram certo

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
