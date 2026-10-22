"""Vigilância dos alertas: a cada ciclo busca as barras recentes de cada ativo com alerta ativo,
dispara quem teve o nível tocado e avisa no Windows.

Só vigia enquanto o servidor está de pé. Ao ligar, o primeiro ciclo cobre o que aconteceu enquanto estava
desligado (com barras maiores quanto mais longo foi o intervalo). O atraso do alerta é o atraso do dado:
Yahoo traz índices e futuros com alguns minutos de atraso; a Binance é quase em tempo real.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from .. import config
from . import evaluate, notify, prices, store

Fetch = Callable[[str, str, datetime, datetime], tuple[pd.DataFrame, str]]
Notifier = Callable[[str, str, str | None], tuple[bool, str]]

_cycle_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_state: dict = {
    "running": False, "interval": config.ALERT_POLL_SECONDS, "last_cycle_at": None,
    "last_error": None, "cycles": 0, "errors": {},
}
FIRST_CYCLE_DELAY = 3.0  # deixa o servidor terminar de subir


def status() -> dict:
    return {**_state, "errors": dict(_state["errors"])}


def toast_text(alert: dict, hit: dict) -> tuple[str, str]:
    verb = "subiu até" if alert["direction"] == "acima" else "caiu até"
    side = "Máxima" if alert["direction"] == "acima" else "Mínima"
    when = hit["bar"].astimezone().strftime("%d/%m %H:%M")
    body = f"{side} de {hit['extreme']:g} na barra de {when}."
    if alert["note"]:
        body += f" {alert['note']}"
    return f"{alert['symbol']} {verb} {alert['price']:g}", body


def check_once(
    now: datetime | None = None, fetch: Fetch | None = None, notifier: Notifier | None = None
) -> list[dict]:
    """Um ciclo de vigilância. Devolve os alertas que dispararam."""
    now = now or datetime.now(timezone.utc)
    fetch = fetch or prices.fetch_window
    notifier = notifier or notify.send
    fired: list[dict] = []
    errors: dict[str, str] = {}

    with _cycle_lock:
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for alert in store.active():
            groups[(alert["market"], alert["symbol"])].append(alert)

        for (market, symbol), items in groups.items():
            try:
                since = min(evaluate.window_start(a, "1m") for a in items)
                bars, interval = fetch(market, symbol, since, now)
            except Exception as exc:  # um ativo com problema não pode travar os outros
                errors[f"{market}:{symbol}"] = str(exc)
                continue
            last_close = float(bars["Close"].iloc[-1]) if len(bars) else None

            for alert in items:
                hit = evaluate.first_touch(alert, bars, interval)
                if hit is None:
                    until = evaluate.checked_until_after(alert, bars, interval)
                    store.touch(alert["id"], until.isoformat() if until else None, last_close)
                    continue
                if not store.mark_triggered(alert["id"], hit["bar"].isoformat(), hit["extreme"]):
                    continue  # já tinha sido disparado/cancelado por outro caminho
                if alert["entry_id"] and alert["kind"] in ("alvo", "invalidacao"):
                    # o plano já se resolveu: o outro nível deixa de fazer sentido
                    store.cancel_for_entry(
                        alert["entry_id"], f"o plano já tocou {alert['kind']}",
                        kinds=("alvo", "invalidacao"), exclude_id=alert["id"],
                    )
                title, body = toast_text(alert, hit)
                ok, detail = notifier(title, body, config.APP_URL)
                store.set_notified(alert["id"], ok, detail)
                fired.append(store.get(alert["id"]))

    _state.update(
        last_cycle_at=now.isoformat(), cycles=_state["cycles"] + 1, errors=errors,
        last_error=next(iter(errors.values()), None),
    )
    return fired


def _loop() -> None:
    if _stop.wait(FIRST_CYCLE_DELAY):
        return
    while not _stop.is_set():
        try:
            check_once()
        except Exception as exc:  # a thread não pode morrer em silêncio
            _state["last_error"] = str(exc)
        _stop.wait(_state["interval"])


def start(interval: float | None = None) -> bool:
    """Liga a vigilância em segundo plano. Devolve False se já estava ligada."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return False
    _stop.clear()
    _state.update(running=True, interval=interval or config.ALERT_POLL_SECONDS)
    _thread = threading.Thread(target=_loop, name="alerts-watcher", daemon=True)
    _thread.start()
    return True


def stop(timeout: float = 5.0) -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout)
    _state["running"] = False
