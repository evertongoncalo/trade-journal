"""Avaliação do plano de uma tese (acerto sem falar de lucro).

Acerto da tese: alvo atingido antes da invalidação, dentro do horizonte. Invalidação primeiro = erro.
Sem nenhum dos dois até o fim do horizonte = expirada (neutro). Medido em R (múltiplos do risco).

Convenções conservadoras:
- Se alvo e invalidação caem na mesma barra, vale a invalidação.
- Gap além do nível executa na abertura da barra (pode dar R pior que -1 ou melhor que o alvo).
- Só entram barras que abrem a partir do momento do registro.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd


@dataclass(frozen=True)
class Plan:
    direction: str  # "alta" | "baixa"
    entry: float
    invalidation: float
    target: float
    start: datetime
    horizon_days: int


@dataclass(frozen=True)
class Outcome:
    status: str  # "aberta" | "alvo" | "invalidada" | "expirada"
    closed_at: datetime | None = None
    exit_price: float | None = None
    r: float | None = None


def validate_plan(plan: Plan) -> None:
    if plan.horizon_days < 1:
        raise ValueError("O horizonte deve ser de pelo menos 1 dia.")
    if plan.direction == "alta":
        if not (plan.invalidation < plan.entry < plan.target):
            raise ValueError("Em alta: invalidação < entrada < alvo.")
    elif plan.direction == "baixa":
        if not (plan.target < plan.entry < plan.invalidation):
            raise ValueError("Em baixa: alvo < entrada < invalidação.")
    else:
        raise ValueError("A direção deve ser 'alta' ou 'baixa'.")


def r_multiple(plan: Plan, exit_price: float) -> float:
    risk = abs(plan.entry - plan.invalidation)
    move = exit_price - plan.entry if plan.direction == "alta" else plan.entry - exit_price
    return move / risk


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def evaluate_plan(plan: Plan, bars: pd.DataFrame, now: datetime | None = None) -> Outcome:
    now = _utc(now or datetime.now(timezone.utc))
    start = _utc(plan.start)
    end = start + timedelta(days=plan.horizon_days)
    window = bars[(bars.index >= start) & (bars.index <= end)]
    long = plan.direction == "alta"

    for ts, row in window.iterrows():
        o, h, l = float(row["Open"]), float(row["High"]), float(row["Low"])
        exit_price, status = None, None
        if long:
            if o <= plan.invalidation:
                exit_price, status = o, "invalidada"
            elif o >= plan.target:
                exit_price, status = o, "alvo"
            elif l <= plan.invalidation:
                exit_price, status = plan.invalidation, "invalidada"
            elif h >= plan.target:
                exit_price, status = plan.target, "alvo"
        else:
            if o >= plan.invalidation:
                exit_price, status = o, "invalidada"
            elif o <= plan.target:
                exit_price, status = o, "alvo"
            elif h >= plan.invalidation:
                exit_price, status = plan.invalidation, "invalidada"
            elif l <= plan.target:
                exit_price, status = plan.target, "alvo"
        if status:
            return Outcome(status, ts.to_pydatetime(), exit_price, r_multiple(plan, exit_price))

    if now >= end and not window.empty:
        last_close = float(window["Close"].iloc[-1])
        return Outcome("expirada", end, last_close, r_multiple(plan, last_close))
    return Outcome("aberta")
