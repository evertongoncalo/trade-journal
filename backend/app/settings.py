"""Configurações do app guardadas no SQLite (chave/valor). Segredos NÃO entram aqui: ficam só no .env."""
from __future__ import annotations

from . import db


def get(key: str, default: str | None = None) -> str | None:
    with db.connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return default if row is None else row["value"]


def set(key: str, value: str) -> None:  # noqa: A001 - o nome do módulo já diz do que se trata
    with db.connect() as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def delete(*keys: str) -> None:
    with db.connect() as con:
        con.executemany("DELETE FROM settings WHERE key = ?", [(k,) for k in keys])
