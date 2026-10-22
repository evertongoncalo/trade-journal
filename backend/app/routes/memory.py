"""Memória da IA: pós-mortem de teses que falharam, casos parecidos e alertas estatísticos (estes, só código)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .. import config, db
from ..ai import client, package as package_mod
from ..ai.client import AIError
from ..memory import causes, context, patterns, postmortem, store
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize
from ..review import blocks
from ..util import clean_json

router = APIRouter(prefix="/memory", tags=["memória"])

AI_HTTP_STATUS = {"sem_chave": 400, "auth": 401, "creditos": 402, "limite": 429}
PM_HTTP_STATUS = {"nao_encontrado": 404, "nao_elegivel": 400, "sem_caminho": 502}
Market = Literal["acoes", "cripto", "forex"]

ENTRY_KEYS = (
    "id", "market", "symbol", "direction", "decision", "setup", "created_at", "status", "closed_at", "r_multiple",
    "early_exit_at", "early_exit_r",
)


def _entry_brief(row: dict, pm: dict | None) -> dict:
    return {**{k: row[k] for k in ENTRY_KEYS}, "trigger": postmortem.trigger_label(row), "postmortem": postmortem.brief(pm)}


@router.get("")
def overview():
    """A visão geral: o que pede pós-mortem, o que já foi classificado e o que o código enxerga de padrão no diário."""
    entries = db.all_entries()
    pms = store.latest_by_entry()
    live = {r["id"] for r in entries}
    pms = {k: v for k, v in pms.items() if k in live}
    eligible = [_entry_brief(r, pms.get(r["id"])) for r in entries if postmortem.trigger_label(r)]
    return clean_json(
        {
            "causas": {"versao": causes.CAUSES_VERSION, "lista": causes.catalog()},
            "elegiveis": eligible,
            "pendentes": sum(1 for e in eligible if e["postmortem"] is None),
            "distribuicao_das_causas": patterns.cause_distribution(pms),
            "alertas": patterns.global_alerts(entries),
            "ia": {
                "configured": client.configured(),
                "model": config.AI_MODEL,
                "prompt_version": postmortem.PM_VERSION,
                "prompt_fingerprint": postmortem.fingerprint(),
                "avg_cost_usd": store.recent_avg_cost(),
            },
        }
    )


@router.get("/prompt")
def show_prompt():
    """O texto fixo do pós-mortem e o esquema da resposta, para ler exatamente o que a IA recebe como instrução."""
    return {
        "version": postmortem.PM_VERSION,
        "fingerprint": postmortem.fingerprint(),
        "causes_version": causes.CAUSES_VERSION,
        "prompt": postmortem.system_prompt(),
        "schema": postmortem.PM_SCHEMA,
    }


@router.post("/postmortem/{entry_id}")
def run_postmortem(entry_id: int):
    """Uma chamada ao modelo (custa dinheiro). O caso precisa ter sido invalidado ou ter saída antecipada."""
    try:
        pm = postmortem.run(entry_id)
    except postmortem.PostmortemError as exc:
        raise HTTPException(PM_HTTP_STATUS.get(exc.kind, 400), exc.message) from exc
    except AIError as exc:
        raise HTTPException(AI_HTTP_STATUS.get(exc.kind, 502), exc.message) from exc
    return clean_json(pm)


@router.get("/postmortem/{entry_id}")
def get_postmortem(entry_id: int):
    """O pós-mortem mais recente do caso, com o pacote que foi enviado ao modelo."""
    pm = store.latest_for_entry(entry_id, with_package=True)
    if pm is None:
        raise HTTPException(404, "Este registro ainda não tem pós-mortem.")
    return clean_json(pm)


@router.get("/asset/{market}/{symbol}")
def asset_memory(market: Market, symbol: str, horizon: int = Query(10, ge=1, le=60), setups: str = ""):
    """O que o diário sabe sobre o estado atual do ativo: histórico, setups, casos parecidos e alertas que se aplicam."""
    try:
        sym = normalize(market, symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        pkg = package_mod.build(market, sym, horizon, {"indicadores", "price_action", "correlacao"})
    except ProviderError as exc:
        raise HTTPException(502, f"Sem dados de preço para ler o estado atual: {exc}") from exc
    stances = blocks.derive(context.snapshot_from_package(pkg))
    names = [s.strip() for s in setups.split(",") if s.strip()]
    entries = db.all_entries()
    return clean_json(
        {
            "estado_atual": {k: v for k, v in stances.items() if v is not None},
            **patterns.asset_memory(entries, store.latest_by_entry(), market, sym, stances, names),
        }
    )
