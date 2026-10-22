"""Pacote de dados da análise com IA. Tudo é calculado por código; a IA só interpreta o que está aqui.

O pacote tem uma parte comum (ativo, saúde dos dados, avisos) e fatias por tema (indicadores, price action, macro,
correlação, fundamentos, par). Cada lente recebe só as fatias dela (ver prompts.LENSES).
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..analysis import indicators, price_action, state_prob
from ..correlation import service as correlation_service
from ..providers import registry
from ..providers.base import ProviderError
from ..providers.symbols import normalize
from ..scanner.universe import stock_names
from ..util import clean_json
from . import fundamentals, macro

DAILY_DAYS = 3650
FIXED_SLUGS = {"^GSPC": "sp500", "DX-Y.NYB": "dxy"}
CORR_KEEP = ("label", "status", "mechanical", "corr_full", "corr_250", "corr_60", "stability", "beta", "move20_target", "move20_other", "other_unit", "z20")
PROB_LABEL = {"alta": "alta", "baixa": "baixa", "indistinta": "indistinta", "sem dados": "sem_dados"}


def _round(x, n: int = 3):
    return None if x is None else round(float(x), n)


def _sig(x, digits: int = 5):
    return None if x is None else float(f"{float(x):.{digits}g}")


def indicators_slice(daily_df, horizon: int) -> dict:
    snap = indicators.snapshot(daily_df)
    tail = indicators.add_indicators(daily_df).tail(10)
    prob = state_prob.conditional_probability(daily_df, horizon)
    return {
        "valores": {k: (_sig(v) if isinstance(v, float) else v) for k, v in snap.items() if k != "bars"},
        "barras_no_historico": snap["bars"],
        "rsi14_ultimos_10": [_round(v, 1) for v in tail["rsi14"]],
        "macd_hist_ultimos_10": [_sig(v, 3) for v in tail["macd_hist"]],
        "probabilidade": {
            "descricao": f"P(preço mais alto em {horizon} dias | estado atual dos indicadores), contagem histórica sem sobreposição",
            "estado": prob["state_label"],
            "ocorrencias": prob["n"],
            "p_alta": _round(prob["p_up"]),
            "ic95": [_round(x) for x in prob["ci"]] if prob["ci"] else None,
            "base_do_ativo": _round(prob["base"]),
            "diferenca_pp": _round(prob["lift_pp"], 1),
            "rotulo": PROB_LABEL[prob["label"]],
            "historico_desde": prob["history_start"],
        },
    }


def correlation_slice(market: str, sym: str) -> dict:
    try:
        panel = correlation_service.panel_payload(market, sym)
    except Exception as exc:
        return {"disponivel": False, "motivo": f"Não consegui calcular as correlações: {exc}"}
    if panel["universe"]["state"] == "vazio":
        return {"disponivel": False, "motivo": "O universo de correlação ainda não foi baixado (botão 'Atualizar universo')."}

    fixed = {FIXED_SLUGS.get(r["symbol"], r["symbol"]): {k: r.get(k) for k in CORR_KEEP} for r in panel["fixed"]}
    stable = [
        {"grupo": g["name"], **{k: i.get(k) for k in ("label", "corr_full", "corr_250", "stability", "beta", "z20")}}
        for g in panel["discovered"]
        for i in g["items"]
        if i["status"] == "estável" and not i["mechanical"]
    ]
    stable.sort(key=lambda x: -abs(x["corr_full"] or 0))
    return {
        "disponivel": True,
        "janela": "~2 anos de retornos diários, fechamentos alinhados às 16h de Nova York",
        "universo_atualizado_em": panel["universe"]["updated_at"],
        "universo_estado": panel["universe"]["state"],
        "referencias_fixas": fixed,
        "descobertas_estaveis": stable[:8],
        "parecer_do_codigo": panel["parecer"]["lines"] if panel["parecer"] else [],
    }


def pair_slice(market: str, sym: str) -> dict:
    if market != "forex":
        return {"disponivel": False, "motivo": "Só se aplica a forex."}
    if sym in ("XAUUSD", "XAGUSD"):
        return {"tipo": "metal precioso cotado em dólar", "ativo": sym[:3], "cotacao": "USD"}
    return {"tipo": "par de moedas", "base": sym[:3], "cotacao": sym[3:]}


def build(market: str, symbol: str, horizon: int, slices: set[str]) -> dict:
    """Monta a parte comum e só as fatias pedidas. Levanta ProviderError se não houver preço do ativo."""
    sym = normalize(market, symbol)
    daily = registry.fetch(market, sym, "1d", DAILY_DAYS)
    try:
        intraday = registry.fetch(market, sym, "1h", 5)
    except ProviderError:
        intraday = None
    live = intraday or daily
    health = {"diario": daily.health(), "intradiario": intraday.health() if intraday else None}

    avisos = list(dict.fromkeys(n for n in (daily.note, intraday.note if intraday else "") if n))  # sem repetir a mesma nota
    age = health["intradiario"]["last_bar_age_minutes"] if health["intradiario"] else None
    if age is not None and age > 120:
        avisos.append("O mercado pode estar fechado: o preço é o do último pregão e a barra de hoje não existe ainda.")
    if intraday is None:
        avisos.append("Sem dado intradiário: o preço é o do último fechamento diário.")

    base = {
        "ativo": {
            "mercado": market,
            "simbolo": sym,
            "nome": stock_names().get(sym) if market == "acoes" else None,
            "preco": _sig(live.df["Close"].iloc[-1]),
            "momento_do_preco_utc": live.last_bar.isoformat() if live.last_bar else None,
            "horizonte_dias": horizon,
            "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "saude_dados": {
            "diario": {
                "fonte": f"{health['diario']['source']}:{health['diario']['symbol_at_source']}",
                "ultima_barra_utc": health["diario"]["last_bar_utc"],
            },
            "intradiario": None if not health["intradiario"] else {
                "idade_da_ultima_barra_min": health["intradiario"]["last_bar_age_minutes"],
            },
        },
        "avisos": avisos,
    }

    out: dict = {}
    if "indicadores" in slices:
        out["indicadores"] = indicators_slice(daily.df, horizon)
    if "price_action" in slices:
        out["price_action"] = price_action.summarize(daily.df)
    if "macro" in slices:
        out["macro"] = macro.snapshot(macro.CRYPTO_KEYS if market == "cripto" else None)
    if "correlacao" in slices:
        out["correlacao"] = correlation_slice(market, sym)
    if "fundamentos" in slices:
        out["fundamentos"] = (
            fundamentals.fetch(sym) if market == "acoes" else {"disponivel": False, "motivo": "Só existe para ações."}
        )
    if "par" in slices:
        out["par"] = pair_slice(market, sym)
    return clean_json({**base, "fatias": out})
