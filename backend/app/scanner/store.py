"""Persistência do scanner: setups, varreduras e ativos encontrados."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import db
from .bars import TIMEFRAMES
from .conditions import normalize_definition
from .. import settings
from .defaults import DEFAULT_SETUPS, DEFAULT_SETUPS_H4, H4_SUFFIX


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- setups ----------


def _setup(row) -> dict:
    d = dict(row)
    return {
        "id": d["id"],
        "name": d["name"],
        "enabled": bool(d["enabled"]),
        "direction": d["direction"],
        "markets": json.loads(d["markets"]),
        "timeframe": d["timeframe"],
        "definition": json.loads(d["definition_json"]),
        "created_at": d["created_at"],
        "updated_at": d["updated_at"],
    }


def list_setups() -> list[dict]:
    with db.connect() as con:
        return [_setup(r) for r in con.execute("SELECT * FROM setups ORDER BY id").fetchall()]


def get_setup(setup_id: int) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM setups WHERE id = ?", (setup_id,)).fetchone()
        return _setup(row) if row else None


def _check_timeframe(timeframe: str) -> None:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Timeframe desconhecido: {timeframe!r} (use {' ou '.join(TIMEFRAMES)})")


def create_setup(
    name: str, enabled: bool, direction: str, markets: list[str], definition: dict, timeframe: str = "D1"
) -> dict:
    definition = normalize_definition(definition)
    _check_timeframe(timeframe)
    now = _now()
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO setups (name, enabled, direction, markets, definition_json, timeframe, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, int(enabled), direction, json.dumps(markets), json.dumps(definition, ensure_ascii=False), timeframe, now, now),
        )
        new_id = int(cur.lastrowid)
    return get_setup(new_id)


def update_setup(
    setup_id: int, name: str, enabled: bool, direction: str, markets: list[str], definition: dict, timeframe: str = "D1"
) -> dict | None:
    definition = normalize_definition(definition)
    _check_timeframe(timeframe)
    with db.connect() as con:
        cur = con.execute(
            "UPDATE setups SET name = ?, enabled = ?, direction = ?, markets = ?, definition_json = ?, timeframe = ?, "
            "updated_at = ? WHERE id = ?",
            (
                name, int(enabled), direction, json.dumps(markets), json.dumps(definition, ensure_ascii=False),
                timeframe, _now(), setup_id,
            ),
        )
        if cur.rowcount == 0:
            return None
    return get_setup(setup_id)


def delete_setup(setup_id: int) -> bool:
    with db.connect() as con:
        return con.execute("DELETE FROM setups WHERE id = ?", (setup_id,)).rowcount > 0


H4_DEFAULTS_FLAG = "defaults_h4_added"  # as versões H4 dos setups iniciais são criadas UMA vez


def _create_default(s: dict) -> None:
    create_setup(s["name"], s["enabled"], s["direction"], s["markets"], s["definition"], s.get("timeframe", "D1"))


def ensure_default_setups() -> None:
    """Cria os setups iniciais (regras do scanner antigo), nos dois timeframes: D1 e H4.

    Banco novo: os seis. Banco que já tinha os três diários: ganha as versões H4 uma única vez, só dos que ainda existem com o
    nome original, e nunca mais (se você apagar um H4 de propósito, ele não volta).
    """
    with db.connect() as con:
        empty = con.execute("SELECT COUNT(*) FROM setups").fetchone()[0] == 0
    if empty:
        for s in [*DEFAULT_SETUPS, *DEFAULT_SETUPS_H4]:
            _create_default(s)
        settings.set(H4_DEFAULTS_FLAG, "1")
    elif settings.get(H4_DEFAULTS_FLAG) is None:
        have = {s["name"] for s in list_setups()}
        for s in DEFAULT_SETUPS_H4:
            if s["name"][: -len(H4_SUFFIX)] in have and s["name"] not in have:
                _create_default(s)
        settings.set(H4_DEFAULTS_FLAG, "1")


# ---------- varreduras e resultados ----------


def create_run(markets: list[str], setups: list[dict]) -> int:
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO scan_runs (started_at, state, markets, setups_json) VALUES (?, 'running', ?, ?)",
            (_now(), json.dumps(markets), json.dumps([s["name"] for s in setups], ensure_ascii=False)),
        )
        return int(cur.lastrowid)


def finish_run(
    run_id: int, state: str, symbols_total: int, symbols_ok: int, errors: dict, as_of: dict, error: str | None = None
) -> None:
    with db.connect() as con:
        con.execute(
            "UPDATE scan_runs SET finished_at = ?, state = ?, symbols_total = ?, symbols_ok = ?, "
            "errors_json = ?, as_of_json = ?, error = ? WHERE id = ?",
            (_now(), state, symbols_total, symbols_ok, json.dumps(errors, ensure_ascii=False), json.dumps(as_of), error, run_id),
        )


def close_orphan_runs() -> None:
    """Varreduras que ficaram 'running' porque o servidor foi encerrado no meio."""
    with db.connect() as con:
        con.execute(
            "UPDATE scan_runs SET state = 'error', finished_at = ?, error = 'interrompida' WHERE state = 'running'",
            (_now(),),
        )


def save_hits(run_id: int, hits: list[dict]) -> None:
    rows = [
        (
            run_id, h["setup_id"], h["setup_name"], h["market"], h["symbol"], h["direction"], h["price"],
            json.dumps(h["details"], ensure_ascii=False), h.get("timeframe", "D1"),
        )
        for h in hits
    ]
    with db.connect() as con:
        con.executemany(
            "INSERT INTO scan_hits (run_id, setup_id, setup_name, market, symbol, direction, price, details_json, timeframe) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _run(row) -> dict:
    d = dict(row)
    errors = json.loads(d["errors_json"])
    return {
        "id": d["id"],
        "started_at": d["started_at"],
        "finished_at": d["finished_at"],
        "state": d["state"],
        "markets": json.loads(d["markets"]),
        "setups": json.loads(d["setups_json"]),
        "symbols_total": d["symbols_total"],
        "symbols_ok": d["symbols_ok"],
        "errors": errors,
        "errors_count": len(errors),
        "as_of": json.loads(d["as_of_json"]),
        "error": d["error"],
    }


def get_run(run_id: int) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM scan_runs WHERE id = ?", (run_id,)).fetchone()
        return _run(row) if row else None


def latest_run() -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM scan_runs WHERE state = 'done' ORDER BY id DESC LIMIT 1").fetchone()
        return _run(row) if row else None


def list_runs(limit: int = 20) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = [_run(r) for r in rows]
    for r in out:
        r.pop("errors", None)  # a lista só interessa na varredura aberta
    return out


def run_hits(run_id: int) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM scan_hits WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d.pop("details_json"))
        out.append(d)
    return out


def mark_hit_opened(hit_id: int) -> bool:
    with db.connect() as con:
        return (
            con.execute(
                "UPDATE scan_hits SET opened_at = COALESCE(opened_at, ?) WHERE id = ?", (_now(), hit_id)
            ).rowcount
            > 0
        )
