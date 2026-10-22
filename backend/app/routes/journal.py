"""Diário de decisões: registro, acompanhamento automático do resultado e saída antecipada."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .. import db
from ..alerts import service as alert_service
from ..journal.evaluate import Plan, evaluate_plan, r_multiple, validate_plan
from ..providers import registry
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize
from ..util import clean_json

router = APIRouter(prefix="/journal", tags=["diário"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _plan(row: dict) -> Plan:
    return Plan(
        direction=row["direction"],
        entry=row["entry_price"],
        invalidation=row["invalidation"],
        target=row["target"],
        start=_parse(row["created_at"]),
        horizon_days=row["horizon_days"],
    )


def _present(row: dict) -> dict:
    d = dict(row)
    d["snapshot"] = json.loads(d.pop("snapshot_json") or "{}")
    d["risk"] = abs(d["entry_price"] - d["invalidation"])
    return clean_json(d)


class EntryIn(BaseModel):
    market: Literal["acoes", "cripto", "forex"]
    symbol: str
    decision: Literal["entrei", "nao_entrei", "observando"]
    direction: Literal["alta", "baixa"]
    entry_price: float = Field(gt=0)
    invalidation: float = Field(gt=0)
    target: float = Field(gt=0)
    horizon_days: int = Field(ge=1, le=365)
    thesis: str = ""
    setup: str = ""
    snapshot: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _plan_consistent(self):
        validate_plan(
            Plan(self.direction, self.entry_price, self.invalidation, self.target, _now(), self.horizon_days)
        )
        return self


class EarlyExitIn(BaseModel):
    price: float = Field(gt=0)
    reason: str = ""


@router.get("")
def list_entries():
    return [_present(r) for r in db.all_entries()]


@router.post("", status_code=201)
def create_entry(body: EntryIn):
    try:
        sym = normalize(body.market, body.symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    data = body.model_dump()
    data["symbol"] = sym
    data["snapshot_json"] = json.dumps(data.pop("snapshot"), ensure_ascii=False, default=str)
    data["created_at"] = _now().isoformat()
    row = db.get_entry(db.insert_entry(data))
    try:  # os alertas dos níveis do plano nunca podem impedir o registro no diário
        created = alert_service.create_plan_alerts(row)
    except Exception:
        created = []
    return {
        **_present(row),
        "alerts": [{"id": a["id"], "kind": a["kind"], "price": a["price"], "direction": a["direction"]} for a in created],
    }


@router.post("/refresh")
def refresh():
    """Reavalia as teses abertas contra o preço que aconteceu depois do registro."""
    now = _now()
    groups: dict[tuple, list[dict]] = {}
    for row in db.all_entries():
        if row["status"] == "aberta":
            groups.setdefault((row["market"], row["symbol"]), []).append(row)

    changed, errors = 0, []
    for (market, symbol), rows in groups.items():
        oldest = min(_parse(r["created_at"]) for r in rows)
        days = max(2, (now - oldest).days + 2)
        try:
            hist = registry.fetch(market, symbol, "1h" if days <= 700 else "1d", days)
        except ProviderError as exc:
            errors.append({"symbol": symbol, "erro": str(exc)})
            continue
        for row in rows:
            out = evaluate_plan(_plan(row), hist.df, now=now)
            fields = {"last_evaluated_at": now.isoformat()}
            if out.status != "aberta":
                changed += 1
                alert_service.cancel_for_entry(row["id"], f"tese encerrada: {out.status}")
                fields.update(
                    status=out.status,
                    closed_at=out.closed_at.isoformat() if out.closed_at else None,
                    exit_price=out.exit_price,
                    r_multiple=out.r,
                )
            db.update_entry(row["id"], **fields)
    return {"avaliadas": sum(len(r) for r in groups.values()), "encerradas": changed, "erros": errors}


@router.post("/{entry_id}/early-exit")
def early_exit(entry_id: int, body: EarlyExitIn):
    row = db.get_entry(entry_id)
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    if row["decision"] != "entrei":
        raise HTTPException(400, "Só registros com decisão 'entrei' têm saída antecipada.")
    if row["early_exit_at"]:
        raise HTTPException(400, "A saída antecipada já foi registrada.")
    db.update_entry(
        entry_id,
        early_exit_at=_now().isoformat(),
        early_exit_price=body.price,
        early_exit_reason=body.reason,
        early_exit_r=r_multiple(_plan(row), body.price),
    )
    alert_service.cancel_for_entry(entry_id, "saída antecipada registrada")
    return _present(db.get_entry(entry_id))


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int):
    if not db.delete_entry(entry_id):
        raise HTTPException(404, "Registro não encontrado")
    alert_service.cancel_for_entry(entry_id, "registro excluído")


def _group(rows: list[dict], key) -> dict:
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(key(r), {"alvo": 0, "invalidada": 0, "expirada": 0, "aberta": 0})
        g[r["status"]] += 1
    for g in groups.values():
        done = g["alvo"] + g["invalidada"]
        g["fechadas"] = done
        g["taxa_acerto"] = g["alvo"] / done if done else None
    return groups


@router.get("/stats")
def stats():
    """Acerto da tese = alvo / (alvo + invalidada). Expiradas e abertas ficam fora da taxa."""
    rows = db.all_entries()
    return {
        "total": len(rows),
        "geral": _group(rows, lambda r: "todas").get("todas"),
        "por_decisao": _group(rows, lambda r: r["decision"]),
        "por_mercado": _group(rows, lambda r: r["market"]),
        "saida_antecipada": sum(1 for r in rows if r["early_exit_at"]),
    }
