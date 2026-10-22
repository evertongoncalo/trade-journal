"""Painel de correlação de um ativo: usado pela rota da ficha e pelo pacote de dados da análise com IA."""
from __future__ import annotations

from ..providers import registry
from ..providers.symbols import yahoo_symbol
from . import engine, store, universe


def panel_payload(market: str, sym: str) -> dict:
    """`sym` já normalizado. Levanta ProviderError se não houver preço do ativo."""
    hist = registry.fetch(market, sym, "1h", store.HOURLY_DAYS)
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
    return {
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
