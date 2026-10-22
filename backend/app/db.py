"""Armazenamento em SQLite (arquivo local)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,              -- UTC, ISO 8601
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    decision TEXT NOT NULL,                -- entrei | nao_entrei | observando
    direction TEXT NOT NULL,               -- alta | baixa
    entry_price REAL NOT NULL,
    invalidation REAL NOT NULL,
    target REAL NOT NULL,
    horizon_days INTEGER NOT NULL,
    thesis TEXT NOT NULL DEFAULT '',
    setup TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'aberta', -- aberta | alvo | invalidada | expirada
    closed_at TEXT,
    exit_price REAL,
    r_multiple REAL,
    early_exit_at TEXT,
    early_exit_price REAL,
    early_exit_reason TEXT,
    early_exit_r REAL,
    last_evaluated_at TEXT
);

-- Fechamentos diários de cada instrumento no instante 16:00 de Nova York (painel de correlação).
CREATE TABLE IF NOT EXISTS closes_ny16 (
    symbol TEXT NOT NULL,
    d TEXT NOT NULL,                       -- data (NY), AAAA-MM-DD
    close REAL NOT NULL,
    PRIMARY KEY (symbol, d)
);
CREATE TABLE IF NOT EXISTS closes_meta (
    symbol TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,              -- UTC, ISO 8601
    rows INTEGER NOT NULL
);
"""

_UPDATABLE = {
    "status", "closed_at", "exit_price", "r_multiple", "last_evaluated_at",
    "early_exit_at", "early_exit_price", "early_exit_reason", "early_exit_r",
}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)


def insert_entry(data: dict) -> int:
    cols = ", ".join(data)
    marks = ", ".join(f":{k}" for k in data)
    with connect() as con:
        cur = con.execute(f"INSERT INTO entries ({cols}) VALUES ({marks})", data)
        return int(cur.lastrowid)


def get_entry(entry_id: int) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None


def all_entries() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM entries ORDER BY created_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]


def update_entry(entry_id: int, **fields) -> None:
    bad = set(fields) - _UPDATABLE
    if bad:
        raise ValueError(f"Campos não atualizáveis: {sorted(bad)}")
    if not fields:
        return
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as con:
        con.execute(f"UPDATE entries SET {sets} WHERE id = :_id", {**fields, "_id": entry_id})


def delete_entry(entry_id: int) -> bool:
    with connect() as con:
        cur = con.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cur.rowcount > 0
