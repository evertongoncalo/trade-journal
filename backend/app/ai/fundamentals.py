"""Fundamentos de ações (só ações), via Yahoo Finance. Dados de analistas ficam separados: são opinião de terceiros."""
from __future__ import annotations

import warnings
from datetime import date, datetime, timezone
from functools import lru_cache

import yfinance as yf

from ..providers.symbols import yahoo_symbol

FIELDS = {
    "nome": "shortName",
    "setor": "sector",
    "industria": "industry",
    "valor_de_mercado_usd": "marketCap",
    "pl_12m": "trailingPE",
    "pl_futuro": "forwardPE",
    "preco_sobre_valor_patrimonial": "priceToBook",
    "ev_sobre_ebitda": "enterpriseToEbitda",
    "margem_liquida": "profitMargins",
    "margem_operacional": "operatingMargins",
    "crescimento_receita": "revenueGrowth",
    "crescimento_lucro": "earningsGrowth",
    "roe": "returnOnEquity",
    "divida_sobre_patrimonio": "debtToEquity",
    "caixa_livre_usd": "freeCashflow",
    "beta": "beta",
}
UNITS_NOTE = (
    "Margens, crescimentos e ROE são frações (0,64 = 64%). `divida_sobre_patrimonio` vem do Yahoo em percentual "
    "(16,97 = 16,97%, não 17 vezes). Valores em US$."
)
ANALYSTS = {"alvo_medio_usd": "targetMeanPrice", "recomendacao": "recommendationKey", "n_analistas": "numberOfAnalystOpinions"}


def _next_earnings(ticker: yf.Ticker, today: date) -> dict:
    """Data do próximo resultado trimestral e quantos dias faltam (None se o Yahoo não informar)."""
    try:
        cal = ticker.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        future = sorted(d for d in (dates or []) if isinstance(d, date) and d >= today)
        if future:
            return {"proximo_resultado": future[0].isoformat(), "dias_ate_o_resultado": (future[0] - today).days}
    except Exception:
        pass
    return {"proximo_resultado": None, "dias_ate_o_resultado": None}


@lru_cache(maxsize=64)
def _fetch_cached(ysym: str, day: str) -> dict:  # `day` entra na chave para o cache vencer todo dia
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ticker = yf.Ticker(ysym)
        info = ticker.info or {}
        if not info or info.get("quoteType") not in (None, "EQUITY"):
            kind = info.get("quoteType") if info else None
            return {"disponivel": False, "motivo": f"Sem fundamentos: o Yahoo não trata este símbolo como ação ({kind or 'sem dados'})."}
        out: dict = {"disponivel": True, "fonte": "Yahoo Finance", "unidades": UNITS_NOTE}
        for key, src in FIELDS.items():
            value = info.get(src)
            out[key] = round(value, 4) if isinstance(value, float) else value
        out.update(_next_earnings(ticker, date.fromisoformat(day)))
        analysts = {key: info.get(src) for key, src in ANALYSTS.items()}
        out["analistas_opiniao_de_terceiros"] = analysts
        return out


def fetch(symbol: str, today: date | None = None) -> dict:
    """`symbol` no formato do app (ex.: BRK-B). Nunca levanta: falha vira `disponivel: False`."""
    today = today or datetime.now(timezone.utc).date()
    ysym = yahoo_symbol("acoes", symbol)[0]
    try:
        return _fetch_cached(ysym, today.isoformat())
    except Exception as exc:
        return {"disponivel": False, "motivo": f"Não consegui os fundamentos no Yahoo: {exc}"}
