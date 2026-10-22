"""Persistência dos pós-mortems. Um caso pode ter vários (se for refeito); vale o último."""
from __future__ import annotations

import json

from .. import db


def save(pm: dict, package: dict) -> int:
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO postmortems (entry_id, created_at, trigger, prompt_version, prompt_fingerprint, causes_version, "
            "model, effort, package_json, result_json, checks_json, cost_usd, prompt_tokens, completion_tokens, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pm["entry_id"], pm["created_at"], pm["trigger"], pm["prompt_version"], pm["prompt_fingerprint"],
                pm["causes_version"], pm["model"], pm["effort"], json.dumps(package, ensure_ascii=False),
                json.dumps(pm["result"], ensure_ascii=False), json.dumps(pm["checks"], ensure_ascii=False),
                pm["cost_usd"], pm["prompt_tokens"], pm["completion_tokens"], pm["duration_ms"],
            ),
        )
        return int(cur.lastrowid)


def _row(r, with_package: bool) -> dict:
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json"))
    d["checks"] = json.loads(d.pop("checks_json"))
    package = json.loads(d.pop("package_json"))
    if with_package:
        d["package"] = package
    return d


def latest_for_entry(entry_id: int, with_package: bool = False) -> dict | None:
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM postmortems WHERE entry_id = ? ORDER BY id DESC LIMIT 1", (entry_id,)
        ).fetchone()
        return _row(row, with_package) if row else None


def latest_by_entry() -> dict[int, dict]:
    """O pós-mortem mais recente de cada caso, sem o pacote."""
    with db.connect() as con:
        rows = con.execute(
            "SELECT * FROM postmortems WHERE id IN (SELECT MAX(id) FROM postmortems GROUP BY entry_id) ORDER BY id DESC"
        ).fetchall()
    return {r["entry_id"]: _row(r, False) for r in rows}


def delete_for_entry(entry_id: int) -> int:
    with db.connect() as con:
        return con.execute("DELETE FROM postmortems WHERE entry_id = ?", (entry_id,)).rowcount


def recent_avg_cost(n: int = 10) -> float | None:
    with db.connect() as con:
        row = con.execute(
            "SELECT AVG(cost_usd) FROM (SELECT cost_usd FROM postmortems WHERE cost_usd IS NOT NULL ORDER BY id DESC LIMIT ?)",
            (n,),
        ).fetchone()
    return None if row[0] is None else float(row[0])
