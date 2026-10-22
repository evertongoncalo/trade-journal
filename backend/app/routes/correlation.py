"""Painel de correlação: ativo contra referências fixas (S&P 500, DXY) e correlações descobertas."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..correlation import engine, store, universe
from ..providers import registry
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize, yahoo_symbol
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
        hist = registry.fetch(market, sym, "1h", store.HOURLY_DAYS)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc

    target_yahoo = yahoo_symbol(market, sym)[0]
    snap = store.snap_ny16(hist.df)

    base = store.load_closes()
    idx = base.index.union(snap.index)
    closes = base.reindex(idx)
    closes[engine.TARGET] = snap.reindex(idx)

    sectors = universe.own_sector_etfs(target_yahoo) if market == "acoes" else frozenset()
    result = engine.build_panel(
        closes,
        universe.CANDIDATES,
        universe.FIXED,
        is_mechanical=lambda other: universe.is_mechanical(target_yahoo, other, sectors),
        exclude={target_yahoo},
    )
    return clean_json(
        {
            "target": {
                "symbol": sym,
                "yahoo": target_yahoo,
                "market": market,
                "observations": int(len(snap)),
                "first": snap.index[0].date() if len(snap) else None,
                "last": snap.index[-1].date() if len(snap) else None,
            },
            "universe": store.universe_state(),
            "refresh": store.status(),
            "params": engine.params(),
            **result,
        }
    )
