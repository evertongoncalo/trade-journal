"""Casos parecidos: os registros já resolvidos do diário cujo estado se parece com o de agora.

A semelhança é uma conta aberta, não um modelo: soma pontos por "mesmo ativo", "mesmo mercado", "setup em comum" e por
cada bloco de código que aponta o MESMO lado (alta ou baixa) nos dois casos. Cada caso devolvido traz os motivos, para você
ver por que ele entrou. Com poucos registros, poucos casos passam do corte; é assim mesmo.
"""
from __future__ import annotations

import json

from ..review import blocks, engine as review
from .path import parse_ts

SAME_ASSET = 3
SAME_MARKET = 1
SHARED_SETUP = 2
SAME_DIRECTION = 1
BLOCK_MATCH = 1
MIN_SCORE = 3
TOP_K = 5

_OPEN = "aberta"


def setups_of(row: dict) -> set[str]:
    return {s.strip() for s in (row.get("setup") or "").split(" + ") if s.strip()}


def stances_of(row: dict) -> dict[str, str | None]:
    try:
        snap = json.loads(row.get("snapshot_json") or "{}")
    except (TypeError, ValueError):
        snap = {}
    return blocks.derive(snap if isinstance(snap, dict) else {})


def score(target: dict, row: dict, row_stances: dict) -> tuple[int, list[str]]:
    """Pontos e motivos de `row` se parecer com o alvo. O alvo traz market, symbol, stances e, se souber, setups e direction."""
    points, reasons = 0, []
    if row["market"] == target["market"]:
        if row["symbol"] == target["symbol"]:
            points += SAME_ASSET
            reasons.append("mesmo ativo")
        else:
            points += SAME_MARKET
            reasons.append("mesmo mercado")
    common = setups_of(row) & set(target.get("setups") or ())
    if common:
        points += SHARED_SETUP
        reasons.append("setup em comum: " + ", ".join(sorted(common)))
    if target.get("direction") and row["direction"] == target["direction"]:
        points += SAME_DIRECTION
        reasons.append(f"mesma direção ({row['direction']})")
    for key, title, _ in blocks.BLOCKS:
        now, then = target["stances"].get(key), row_stances.get(key)
        if now in ("alta", "baixa") and now == then:
            points += BLOCK_MATCH
            reasons.append(f"{title}: {now}")
    return points, reasons


def days_to_outcome(row: dict) -> float | None:
    if not row.get("closed_at"):
        return None
    return round((parse_ts(row["closed_at"]) - parse_ts(row["created_at"])).total_seconds() / 86400, 1)


def case_view(row: dict, points: int, reasons: list[str], pm: dict | None, stances: dict) -> dict:
    return {
        "id": row["id"],
        "mercado": row["market"],
        "simbolo": row["symbol"],
        "direcao": row["direction"],
        "decisao": row["decision"],
        "registrado_em": row["created_at"],
        "setup": row.get("setup") or "",
        "desfecho": row["status"],
        "r": row.get("r_multiple"),
        "dias_ate_desfecho": days_to_outcome(row),
        "pontos": points,
        "por_que_parecido": reasons,
        "blocos": {k: v for k, v in stances.items() if v is not None},
        "pos_mortem": None
        if pm is None
        else {"causa": pm["result"]["causa_principal"], "visibilidade": pm["result"]["visibilidade"], "confianca": pm["result"]["confianca"]},
    }


def find(
    target: dict, entries: list[dict], postmortems: dict[int, dict] | None = None, *, k: int = TOP_K, min_score: int = MIN_SCORE,
    exclude_id: int | None = None,
) -> dict:
    """Os `k` casos mais parecidos (resolvidos ou expirados) e o resumo estatístico de TODOS os que passam do corte."""
    postmortems = postmortems or {}
    scored = []
    for row in entries:
        if row["status"] == _OPEN or row["id"] == exclude_id:
            continue
        stances = stances_of(row)
        points, reasons = score(target, row, stances)
        if points >= min_score:
            scored.append((points, row, reasons, stances))
    scored.sort(key=lambda t: (t[0], t[1]["created_at"]), reverse=True)  # mais pontos primeiro; empate: o mais recente
    matched = [row for _, row, _, _ in scored]
    return {
        "casos": [case_view(r, p, why, postmortems.get(r["id"]), st) for p, r, why, st in scored[:k]],
        "total_parecidos": len(matched),
        "grupo": {
            "todos": review.cell(matched),
            "teses_de_alta": review.cell([r for r in matched if r["direction"] == "alta"]),
            "teses_de_baixa": review.cell([r for r in matched if r["direction"] == "baixa"]),
        },
        "criterio": {"minimo_de_pontos": min_score, "maximo_de_casos": k},
    }
