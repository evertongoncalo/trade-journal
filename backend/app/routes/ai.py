"""Análise com IA: roda as lentes do mercado sobre o pacote de dados e guarda o resultado."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..ai import client, prompts, runner, store
from ..ai.client import AIError
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize
from ..util import clean_json

router = APIRouter(prefix="/ai", tags=["ia"])

# erro -> código HTTP; o texto de cada erro já vem pronto para o usuário
HTTP_STATUS = {"sem_chave": 400, "auth": 401, "creditos": 402, "limite": 429}


class AnalyzeIn(BaseModel):
    market: Literal["acoes", "cripto", "forex"]
    symbol: str
    horizon: int = Field(default=10, ge=1, le=60)
    memory: bool = False  # usa o prompt v2 e entrega casos parecidos do diário (sem texto livre) às lentes


@router.get("/status")
def status():
    return {
        "configured": client.configured(),
        "model": config.AI_MODEL,
        "effort": config.AI_REASONING_EFFORT or None,
        "prompt_version": prompts.PROMPT_VERSION,
        "prompt_fingerprint": prompts.fingerprint(),
        "memory_prompt_version": "v2",
        "memory_prompt_fingerprint": prompts.fingerprint("v2"),
        "lenses": {m: [{"id": i, "title": prompts.LENSES[i].title} for i in ids] for m, ids in prompts.MARKET_LENSES.items()},
        "avg_cost_usd": store.recent_avg_cost(),
    }


@router.get("/prompts")
def show_prompts(version: str = prompts.PROMPT_VERSION):
    """Os textos fixos de uma versão (v1 padrão; v2 = com memória), para ler exatamente o que a IA recebe como instrução."""
    if version not in prompts.PROMPT_VERSIONS:
        raise HTTPException(404, f"Versão desconhecida: {version!r}")
    return {
        "version": version,
        "fingerprint": prompts.fingerprint(version),
        "schema": prompts.LENS_SCHEMA,
        "prompts": prompts.all_prompts(version),
    }


@router.post("/analyze")
def analyze(body: AnalyzeIn):
    try:
        sym = normalize(body.market, body.symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        result = runner.analyze(body.market, sym, body.horizon, memory=body.memory)
    except AIError as exc:
        raise HTTPException(HTTP_STATUS.get(exc.kind, 502), exc.message) from exc
    except ProviderError as exc:
        raise HTTPException(502, f"Sem dados de preço para montar o pacote: {exc}") from exc
    return clean_json(result)


@router.get("/analyses")
def list_analyses(market: str, symbol: str, limit: int = 10):
    try:
        sym = normalize(market, symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    return clean_json(store.list_for_asset(market, sym, min(max(limit, 1), 50)))


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int):
    found = store.get(analysis_id)
    if found is None:
        raise HTTPException(404, "Análise não encontrada")
    return clean_json(found)
