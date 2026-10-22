"""O que o preço fez depois do registro e o que as referências fizeram no mesmo período. Tudo por código, sem IA.

Os valores vão em múltiplos do risco (R = |entrada − invalidação|), a mesma régua do diário. A granularidade é a das
barras que o provedor entrega (1 hora para casos de até ~700 dias; senão, diário): um toque no nível só é conhecido
com a precisão da barra.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..ai.macro import CRYPTO_KEYS, MACRO

MAX_DAILY_POINTS = 30
# Um movimento de referência só é "notável" acima disto (heurística do app, não uma verdade de mercado).
NOTABLE_PCT = 3.0
NOTABLE_VIX_PCT = 15.0
NOTABLE_YIELD_PTS = 0.15


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def case_window(entry: dict, now: datetime) -> tuple[datetime, datetime]:
    """(início, fim) do caso: até o fechamento da tese; se ainda não fechou, até agora (no máximo o fim do horizonte)."""
    start = parse_ts(entry["created_at"])
    horizon_end = start + timedelta(days=entry["horizon_days"])
    if entry.get("closed_at"):
        return start, parse_ts(entry["closed_at"])
    return start, min(now, horizon_end)


def _r(entry: dict, price: float) -> float:
    risk = abs(entry["entry_price"] - entry["invalidation"])
    move = price - entry["entry_price"] if entry["direction"] == "alta" else entry["entry_price"] - price
    return move / risk


def _excursions(entry: dict, bars: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(excursão a favor, excursão contra) de cada barra, em R (contra é negativa)."""
    e, risk = entry["entry_price"], abs(entry["entry_price"] - entry["invalidation"])
    if entry["direction"] == "alta":
        return (bars["High"] - e) / risk, (bars["Low"] - e) / risk
    return (e - bars["Low"]) / risk, (e - bars["High"]) / risk


def _first_touch(entry: dict, bars: pd.DataFrame, level: float, against: bool) -> str | None:
    """Início da primeira barra que tocou o nível (a invalidação ou o alvo), ou None."""
    long = entry["direction"] == "alta"
    # invalidação: abaixo na alta, acima na baixa. Alvo: o contrário.
    below = long == against
    hit = bars["Low"] <= level if below else bars["High"] >= level
    if not hit.any():
        return None
    return bars.index[hit.to_numpy().argmax()].isoformat()


def _daily_r(entry: dict, bars: pd.DataFrame) -> list[dict]:
    closes = bars["Close"].groupby(bars.index.date).last()
    points = [{"d": d.isoformat(), "r": round(_r(entry, float(c)), 2)} for d, c in closes.items()]
    if len(points) > MAX_DAILY_POINTS:  # caso longo: amostra espaçada, sempre com a primeira e a última
        step = (len(points) - 1) / (MAX_DAILY_POINTS - 1)
        points = [points[round(i * step)] for i in range(MAX_DAILY_POINTS)]
    return points


def path_summary(entry: dict, bars: pd.DataFrame, now: datetime | None = None, granularity: str = "1h") -> dict:
    """Caminho do preço no caso e, havendo saída antecipada, o que aconteceu depois dela. `bars` tem índice UTC."""
    now = now or datetime.now(timezone.utc)
    start, end = case_window(entry, now)
    horizon_end = min(now, parse_ts(entry["created_at"]) + timedelta(days=entry["horizon_days"]))
    case_bars = bars[(bars.index >= start) & (bars.index <= end)]
    if case_bars.empty:
        return {"disponivel": False, "motivo": "O provedor não tem barras de preço para o período do caso."}

    fav, adv = _excursions(entry, case_bars)
    out: dict = {
        "disponivel": True,
        "granularidade": granularity,
        "barras": int(len(case_bars)),
        "periodo": {"de": start.isoformat(), "ate": end.isoformat()},
        "dias_ate_o_desfecho": round((end - start).total_seconds() / 86400, 1) if entry.get("closed_at") else None,
        "excursao_a_favor_max_R": round(float(fav.max()), 2),
        "excursao_contra_max_R": round(float(adv.min()), 2),
        "invalidacao_tocada_em": _first_touch(entry, case_bars, entry["invalidation"], against=True),
        "alvo_tocado_em": _first_touch(entry, case_bars, entry["target"], against=False),
        "trajetoria_diaria_R": _daily_r(entry, case_bars),
        "saida_antecipada": None,
    }

    if entry.get("early_exit_at"):
        exit_at = parse_ts(entry["early_exit_at"])
        before = bars[(bars.index >= start) & (bars.index < exit_at)]
        after = bars[(bars.index >= exit_at) & (bars.index <= horizon_end)]
        early: dict = {
            "quando": exit_at.isoformat(),
            "preco": entry["early_exit_price"],
            "r": None if entry.get("early_exit_r") is None else round(entry["early_exit_r"], 2),
            "depois_do_fechamento_da_tese": bool(entry.get("closed_at")) and exit_at > parse_ts(entry["closed_at"]),
            "invalidacao_tocada_antes": _first_touch(entry, before, entry["invalidation"], against=True) is not None
            if not before.empty
            else False,
            "depois": None,
        }
        if not after.empty:
            a_fav, a_adv = _excursions(entry, after)
            early["depois"] = {
                "barras": int(len(after)),
                "ate": after.index[-1].isoformat(),
                "excursao_a_favor_max_R": round(float(a_fav.max()), 2),
                "excursao_contra_max_R": round(float(a_adv.min()), 2),
                "invalidacao_tocada_em": _first_touch(entry, after, entry["invalidation"], against=True),
                "alvo_tocado_em": _first_touch(entry, after, entry["target"], against=False),
                "ultimo_fechamento_R": round(_r(entry, float(after["Close"].iloc[-1])), 2),
            }
        out["saida_antecipada"] = early
    return out


def _notable(key: str, unit: str, change: float) -> bool:
    if unit == "pts":
        return abs(change) >= NOTABLE_YIELD_PTS
    return abs(change) >= (NOTABLE_VIX_PCT if key == "vix" else NOTABLE_PCT)


def _completed_through(ts: datetime) -> pd.Timestamp:
    """Último dia cujo fechamento das 16h de Nova York já tinha acontecido em `ts` (data sem fuso, como o índice dos closes)."""
    local = pd.Timestamp(ts).tz_convert("America/New_York")
    day = local.normalize().tz_localize(None)
    return day if local.hour >= 16 else day - pd.Timedelta(days=1)


def reference_moves(closes: pd.DataFrame, start: datetime, end: datetime, market: str) -> dict:
    """Variação de dólar, juros, VIX, índices etc. entre o último fechamento das 16h NY completo antes do registro e o último
    antes do fim do caso. Só entram fechamentos que já tinham acontecido: um caso de poucas horas, sem nenhum fechamento
    no meio, fica sem referências (usar o fechamento do dia seria olhar para o futuro)."""
    if closes.empty:
        return {"disponivel": False, "motivo": "O universo de correlação não foi baixado: sem referências para o período."}
    first, last = _completed_through(start), _completed_through(end)
    items, notable = {}, []
    for key, sym, name, unit in MACRO:
        if (market == "cripto" and key not in CRYPTO_KEYS) or sym not in closes.columns:
            continue
        s = closes[sym].dropna()
        before, upto = s[s.index <= first], s[s.index <= last]
        if before.empty or upto.empty or upto.index[-1] <= before.index[-1]:
            continue
        a, b = float(before.iloc[-1]), float(upto.iloc[-1])
        change = round(b - a, 3) if unit == "pts" else round((b / a - 1) * 100, 2)
        items[key] = {
            "nome": name, "variacao": change, "unidade": "pts" if unit == "pts" else "%",
            "de": before.index[-1].date().isoformat(), "ate": upto.index[-1].date().isoformat(),  # cada série tem os seus dias úteis
        }
        if _notable(key, unit, change):
            notable.append(key)
    if not items:
        return {
            "disponivel": False,
            "motivo": "O período do caso não inclui um fechamento das 16h de Nova York completo, ou não está coberto "
            "pelo universo de correlação (cerca de 2 anos).",
        }
    return {
        "disponivel": True,
        "de": min(i["de"] for i in items.values()),
        "ate": max(i["ate"] for i in items.values()),
        "instrumentos": items,
        "notaveis": notable,
        "criterio_de_notavel": f"≥ {NOTABLE_PCT}% (VIX ≥ {NOTABLE_VIX_PCT}%; juros ≥ {NOTABLE_YIELD_PTS} pontos)",
    }
