"""Persistência dos alertas de preço."""
from __future__ import annotations

from datetime import datetime, timezone

from .. import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _present(row) -> dict:
    d = dict(row)
    last = d.get("last_price")
    d["distance_pct"] = (d["price"] - last) / last * 100 if last else None  # quanto falta até o nível
    d["notify_ok"] = None if d["notify_ok"] is None else bool(d["notify_ok"])
    return d


def create(
    market: str,
    symbol: str,
    price: float,
    direction: str,
    note: str = "",
    kind: str = "avulso",
    entry_id: int | None = None,
    base_price: float | None = None,
) -> dict:
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO alerts (created_at, market, symbol, price, direction, note, kind, entry_id, base_price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), market, symbol, price, direction, note, kind, entry_id, base_price),
        )
        new_id = int(cur.lastrowid)
    return get(new_id)


def get(alert_id: int) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return _present(row) if row else None


def list_all(limit: int = 300) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_present(r) for r in rows]


def active() -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM alerts WHERE status = 'ativo' ORDER BY id").fetchall()
        return [_present(r) for r in rows]


def counts() -> dict:
    with db.connect() as con:
        active_n = con.execute("SELECT COUNT(*) FROM alerts WHERE status = 'ativo'").fetchone()[0]
        pending = con.execute(
            "SELECT COUNT(*) FROM alerts WHERE status = 'disparado' AND response IS NULL"
        ).fetchone()[0]
    return {"active": active_n, "pending": pending}


def mark_triggered(alert_id: int, bar_start: str, extreme: float) -> bool:
    """Marca como disparado. Só vale uma vez: devolve False se o alerta já não estava ativo."""
    with db.connect() as con:
        cur = con.execute(
            "UPDATE alerts SET status = 'disparado', triggered_at = ?, trigger_bar = ?, triggered_price = ? "
            "WHERE id = ? AND status = 'ativo'",
            (_now(), bar_start, extreme, alert_id),
        )
        return cur.rowcount > 0


def set_notified(alert_id: int, ok: bool, detail: str) -> None:
    with db.connect() as con:
        con.execute(
            "UPDATE alerts SET notified_at = ?, notify_ok = ?, notify_detail = ? WHERE id = ?",
            (_now(), int(ok), detail[:300], alert_id),
        )


def touch(alert_id: int, checked_until: str | None, last_price: float | None) -> None:
    """Registra até onde a vigilância já olhou e o último preço visto."""
    with db.connect() as con:
        con.execute(
            "UPDATE alerts SET checked_until = COALESCE(?, checked_until), last_price = COALESCE(?, last_price), "
            "last_checked_at = ? WHERE id = ? AND status = 'ativo'",
            (checked_until, last_price, _now(), alert_id),
        )


def cancel(alert_id: int, reason: str = "cancelado pelo usuário") -> bool:
    with db.connect() as con:
        cur = con.execute(
            "UPDATE alerts SET status = 'cancelado', cancel_reason = ? WHERE id = ? AND status = 'ativo'",
            (reason, alert_id),
        )
        return cur.rowcount > 0


def cancel_for_entry(
    entry_id: int, reason: str, kinds: tuple[str, ...] | None = None, exclude_id: int | None = None
) -> int:
    sql = "UPDATE alerts SET status = 'cancelado', cancel_reason = ? WHERE entry_id = ? AND status = 'ativo'"
    params: list = [reason, entry_id]
    if kinds:
        sql += f" AND kind IN ({', '.join('?' for _ in kinds)})"
        params += list(kinds)
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    with db.connect() as con:
        return con.execute(sql, params).rowcount


def respond(alert_id: int, response: str, note: str = "") -> bool:
    with db.connect() as con:
        cur = con.execute(
            "UPDATE alerts SET response = ?, response_note = ?, response_at = ? WHERE id = ? AND status = 'disparado'",
            (response, note, _now(), alert_id),
        )
        return cur.rowcount > 0


def delete(alert_id: int) -> bool:
    with db.connect() as con:
        return con.execute("DELETE FROM alerts WHERE id = ?", (alert_id,)).rowcount > 0
