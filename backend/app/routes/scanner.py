"""Scanner: setups do usuário, varredura do universo e lista dos ativos encontrados."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..scanner import runner, store
from ..scanner.conditions import catalog_payload
from ..scanner.universe import stock_names
from ..util import clean_json

router = APIRouter(prefix="/scanner", tags=["scanner"])

Market = Literal["acoes", "cripto", "forex"]


class CondIn(BaseModel):
    type: str
    params: dict[str, float] = Field(default_factory=dict)


class FiltersIn(BaseModel):
    min_price: float = Field(default=0, ge=0)
    min_dollar_volume: float = Field(default=0, ge=0)


class DefinitionIn(BaseModel):
    required: list[CondIn] = Field(default_factory=list)
    confirmations: list[CondIn] = Field(default_factory=list)
    min_confirmations: int = Field(default=0, ge=0)
    filters: FiltersIn = Field(default_factory=FiltersIn)


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    direction: Literal["alta", "baixa"]
    markets: list[Market] = Field(min_length=1)
    timeframe: Literal["D1", "H4"] = "D1"
    definition: DefinitionIn


class RunIn(BaseModel):
    markets: list[Market] | None = None


@router.get("/catalog")
def catalog():
    return catalog_payload()


@router.get("/setups")
def list_setups():
    return store.list_setups()


@router.post("/setups", status_code=201)
def create_setup(body: SetupIn):
    try:
        return store.create_setup(
            body.name, body.enabled, body.direction, body.markets, body.definition.model_dump(), body.timeframe
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/setups/{setup_id}")
def update_setup(setup_id: int, body: SetupIn):
    try:
        updated = store.update_setup(
            setup_id, body.name, body.enabled, body.direction, body.markets, body.definition.model_dump(), body.timeframe
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "Setup não encontrado")
    return updated


@router.delete("/setups/{setup_id}", status_code=204)
def delete_setup(setup_id: int):
    if not store.delete_setup(setup_id):
        raise HTTPException(404, "Setup não encontrado")


@router.post("/run")
def run(body: RunIn | None = None):
    markets = (body.markets if body and body.markets else None) or ["acoes", "cripto", "forex"]
    enabled = [s for s in store.list_setups() if s["enabled"] and set(s["markets"]) & set(markets)]
    if not enabled:
        raise HTTPException(400, "Nenhum setup habilitado para os mercados escolhidos.")
    started = runner.start_run(markets)
    return {"started": started, "status": runner.status()}


@router.get("/status")
def status():
    return runner.status()


def _present_hits(hits: list[dict]) -> list[dict]:
    names = stock_names()
    return [{**h, "name": names.get(h["symbol"]) if h["market"] == "acoes" else None} for h in hits]


@router.get("/runs")
def list_runs():
    return store.list_runs()


@router.get("/runs/latest")
def latest():
    run_ = store.latest_run()
    if run_ is None:
        return {"run": None, "hits": []}
    return clean_json({"run": run_, "hits": _present_hits(store.run_hits(run_["id"]))})


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    run_ = store.get_run(run_id)
    if run_ is None:
        raise HTTPException(404, "Varredura não encontrada")
    return clean_json({"run": run_, "hits": _present_hits(store.run_hits(run_id))})


@router.post("/hits/{hit_id}/opened", status_code=204)
def hit_opened(hit_id: int):
    if not store.mark_hit_opened(hit_id):
        raise HTTPException(404, "Resultado não encontrado")
