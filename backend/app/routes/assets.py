"""Ficha do ativo: preço, saúde dos dados, indicadores e inclinação probabilística."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..analysis import indicators, price_action, state_prob
from ..providers import registry
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize, tradingview_symbol, yahoo_symbol
from ..providers.yahoo import exchange_of
from ..util import clean_json

router = APIRouter(tags=["ativo"])

PRICE_ACTION_KEYS = ("estrutura", "variacao_pct", "posicao_no_range_52s", "dist_maxima_52s_pct", "dist_minima_52s_pct")

DAILY_DAYS = 3650  # ~10 anos de histórico diário


@router.get("/asset/{market}/{symbol}")
def get_asset(market: str, symbol: str, horizon: int = Query(10, ge=1, le=60)):
    try:
        sym = normalize(market, symbol)
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        daily = registry.fetch(market, sym, "1d", DAILY_DAYS)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    try:
        intraday = registry.fetch(market, sym, "1h", 5)
    except ProviderError:
        intraday = None

    live = intraday or daily
    exchange = exchange_of(yahoo_symbol(market, sym)[0]) if market == "acoes" else None

    return clean_json(
        {
            "market": market,
            "symbol": sym,
            "price": float(live.df["Close"].iloc[-1]),
            "price_time": live.last_bar,
            "tradingview_symbol": tradingview_symbol(market, sym, exchange),
            "health": {"daily": daily.health(), "intraday": intraday.health() if intraday else None},
            "snapshot": indicators.snapshot(daily.df),
            "probability": state_prob.conditional_probability(daily.df, horizon),
            "price_action": _price_action(daily.df),
        }
    )


def _price_action(df) -> dict | None:
    """Resumo compacto da estrutura de preço (vai no snapshot do diário); None se o histórico não permite."""
    try:
        full = price_action.summarize(df)
    except Exception:
        return None
    return {k: full[k] for k in PRICE_ACTION_KEYS}
