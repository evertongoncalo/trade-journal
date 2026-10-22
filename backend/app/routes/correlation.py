"""Painel de correlação: ativo contra referências fixas (S&P 500, DXY) e correlações descobertas."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..correlation import service, store
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize
from ..util import clean_json

router = APIRouter(tags=["correlação"])


@router.get("/correlation/status")
def refresh_status():
    return clean_json({"refresh": store.status(), "universe": store.universe_state()})


@router.post("/correlation/refresh")
def refresh_universe():
    """Baixa o universo de candidatos em segundo plano (1 a 2 minutos)."""
    started = store.start_refresh()
    return clean_json({"started": started, "refresh": store.status()})


@router.get("/correlation/{market}/{symbol}")
def panel(market: str, symbol: str):
    try:
        sym = normalize(market, symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return clean_json(service.panel_payload(market, sym))
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
