"""Persistência das análises com IA."""
from __future__ import annotations

import json

from .. import db


def save(a: dict, package: dict) -> int:
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO ai_analyses (created_at, market, symbol, horizon_days, prompt_version, prompt_fingerprint, "
            "model, effort, package_json, lenses_json, cost_usd, prompt_tokens, completion_tokens, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                a["created_at"], a["market"], a["symbol"], a["horizon_days"], a["prompt_version"],
                a["prompt_fingerprint"], a["model"], a["effort"],
                json.dumps(package, ensure_ascii=False), json.dumps(a["lenses"], ensure_ascii=False),
                a["cost_usd"], a["prompt_tokens"], a["completion_tokens"], a["duration_ms"],
            ),
        )
        return int(cur.lastrowid)


def _row(r, with_package: bool) -> dict:
    d = dict(r)
    d["lenses"] = json.loads(d.pop("lenses_json"))
    package = json.loads(d.pop("package_json"))
    if with_package:
        d["package"] = package
    return d


def get(analysis_id: int) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM ai_analyses WHERE id = ?", (analysis_id,)).fetchone()
        return _row(row, with_package=True) if row else None


def list_for_asset(market: str, symbol: str, limit: int = 10) -> list[dict]:
    with db.connect() as con:
        rows = con.execute(
            "SELECT * FROM ai_analyses WHERE market = ? AND symbol = ? ORDER BY id DESC LIMIT ?", (market, symbol, limit)
        ).fetchall()
        return [_row(r, with_package=False) for r in rows]


def recent_avg_cost(n: int = 10) -> float | None:
    """Custo médio (US$) das últimas análises que informaram custo."""
    with db.connect() as con:
        row = con.execute(
            "SELECT AVG(cost_usd) FROM (SELECT cost_usd FROM ai_analyses WHERE cost_usd IS NOT NULL ORDER BY id DESC LIMIT ?)",
            (n,),
        ).fetchone()
    return None if row[0] is None else float(row[0])
