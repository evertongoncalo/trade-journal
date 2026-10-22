"""Motor do painel de correlação (só código, sem IA).

Recebe fechamentos alinhados (colunas = instrumentos + 'ALVO', índice = datas) e calcula, para cada candidato:
correlação de retornos em várias janelas, estabilidade, beta, concordância recente e o descolamento em 20 dias.

Limites a ter em mente: ~2 anos de dados (um regime só); correlação não é causa; muitas coisas correlacionam
com "o mercado" em geral, por isso o painel agrupa por fator e marca relações mecânicas.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

from .universe import YIELD_SYMBOLS, Instrument

TARGET = "ALVO"
ROLL = 60  # janela móvel (dias) para medir estabilidade
RECENT = 20  # janela do descolamento recente (dias)
STABLE_SHARE = 0.80  # fração mínima de janelas com o mesmo sinal
MIN_ABS_CORR = 0.30
MIN_OBS = 120  # mínimo de observações por par
MIN_R2_FOR_GAP = 0.05  # abaixo disso, "o modelo esperava X%" é ruído e o parecer não compara
REBASE_DAYS = 120
TOP_PER_GROUP = 8


def params() -> dict:
    return {
        "roll_days": ROLL,
        "recent_days": RECENT,
        "stable_share": STABLE_SHARE,
        "min_abs_corr": MIN_ABS_CORR,
        "min_obs": MIN_OBS,
        "alignment": "16:00 America/New_York",
    }


def _num(x) -> float | None:
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else x


def _pt(x: float, digits: int = 2, sign: bool = False) -> str:
    s = f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"
    return s.replace(".", ",")


def _returns(sub: pd.DataFrame) -> pd.DataFrame:
    """Retornos diários: variação em pontos para juros, percentual para o resto."""
    out = pd.DataFrame(index=sub.index)
    for c in sub.columns:
        out[c] = sub[c].diff() if c in YIELD_SYMBOLS else sub[c].pct_change()
    return out.dropna()


def _last_corr(a: pd.Series, b: pd.Series, n: int) -> float | None:
    return _num(a.iloc[-n:].corr(b.iloc[-n:])) if len(a) >= n else None


def _residual_gap(ra: pd.Series, rb: pd.Series) -> tuple[float | None, float | None]:
    """(beta, z-score do descolamento de 20 dias): quanto o ativo se afastou do que a referência explica."""
    var_b = rb.var()
    if not var_b > 0:
        return None, None
    beta = ra.cov(rb) / var_b
    resid = ra - (ra.mean() - beta * rb.mean() + beta * rb)
    gap = resid.rolling(RECENT).sum().dropna()
    if len(gap) < 30 or not gap.std() > 0:
        return float(beta), None
    return float(beta), float((gap.iloc[-1] - gap.mean()) / gap.std())


def pair_row(closes: pd.DataFrame, other: str) -> dict | None:
    if other not in closes.columns or TARGET not in closes.columns:
        return None
    sub = closes[[TARGET, other]].dropna()
    if len(sub) < MIN_OBS + 1:
        return None
    r = _returns(sub)
    ra, rb = r[TARGET], r[other]
    full = ra.corr(rb)
    if math.isnan(full):
        return None
    roll = ra.rolling(ROLL).corr(rb).dropna()
    stability = float((np.sign(roll) == np.sign(full)).mean()) if len(roll) else None
    wk = _returns(sub.resample("W-FRI").last().dropna())
    weekly = _num(wk[TARGET].corr(wk[other])) if len(wk) >= 20 else None
    beta, z20 = _residual_gap(ra, rb)

    k = min(RECENT, len(sub) - 1)
    move_t = float(sub[TARGET].iloc[-1] / sub[TARGET].iloc[-1 - k] - 1) * 100
    if other in YIELD_SYMBOLS:
        move_o, unit, tiny_o = float(sub[other].iloc[-1] - sub[other].iloc[-1 - k]), "pts", 0.05
    else:
        move_o, unit, tiny_o = float(sub[other].iloc[-1] / sub[other].iloc[-1 - k] - 1) * 100, "%", 0.5
    if abs(move_t) < 0.5 or abs(move_o) < tiny_o:
        agree = "indefinido"
    else:
        agree = "concordam" if np.sign(full) * np.sign(move_o) == np.sign(move_t) else "divergem"

    return {
        "corr_full": _num(full),
        "corr_250": _last_corr(ra, rb, 250),
        "corr_60": _last_corr(ra, rb, 60),
        "corr_20": _last_corr(ra, rb, 20),
        "roll_min": _num(roll.min()) if len(roll) else None,
        "roll_max": _num(roll.max()) if len(roll) else None,
        "stability": stability,
        "weekly": weekly,
        "beta": _num(beta),
        "n": int(len(r)),
        "move20_target": move_t,
        "move20_other": move_o,
        "other_unit": unit,
        "agree": agree,
        "z20": _num(z20),
    }


def classify(row: dict, mechanical: bool) -> str:
    if mechanical:
        return "mecânica"
    c, stab, weekly = row["corr_full"], row["stability"], row["weekly"]
    stable = (
        stab is not None and stab >= STABLE_SHARE and abs(c) >= MIN_ABS_CORR
        and weekly is not None and np.sign(weekly) == np.sign(c)
    )
    return "estável" if stable else "sem relação estável"


def _z_text(z: float) -> str:
    if abs(z) < 1:
        return "dentro do normal"
    return "divergência relevante" if abs(z) < 2 else "divergência forte"


def _parecer(closes: pd.DataFrame, fixed_rows: list[dict], refs: list[tuple[str, str]]) -> dict | None:
    """Texto gerado por regras a partir dos números (sem IA)."""
    lines: list[str] = []
    for row in fixed_rows:
        label, st = row["label"], row["status"]
        if st == "mecânica":
            lines.append(f"{label}: relação mecânica (compõe ou é composto pelo ativo); fora do parecer.")
        elif st == "sem dados":
            lines.append(f"{label}: sem dados suficientes.")
        elif st == "estável":
            lines.append(
                f"{label}: correlação {_pt(row['corr_full'], 2, True)} (60d: {_pt(row['corr_60'], 2, True)}; "
                f"faixa {_pt(row['roll_min'], 2, True)} a {_pt(row['roll_max'], 2, True)}), "
                f"mesmo sinal em {row['stability'] * 100:.0f}% das janelas; beta {_pt(row['beta'], 1)}."
            )
        else:
            lines.append(
                f"{label}: sem relação estável (correlação {_pt(row['corr_full'], 2, True)}; o sinal muda em "
                f"{(1 - (row['stability'] or 0)) * 100:.0f}% das janelas de 60 dias)."
            )

    result: dict = {
        "lines": lines, "refs_used": [lab for _, lab in refs],
        "r2": None, "r2_first": None, "expected20_pp": None, "actual20_pp": None, "gap20_pp": None, "z20": None,
    }
    if not refs:
        return result
    aligned = closes[[TARGET] + [s for s, _ in refs]].dropna()
    if len(aligned) < MIN_OBS + 1:
        return result
    r = _returns(aligned)
    y = r[TARGET].to_numpy()
    X = np.column_stack([np.ones(len(r))] + [r[s].to_numpy() for s, _ in refs])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    fit = X @ coef
    resid = pd.Series(y - fit, index=r.index)
    r2 = 1 - resid.var() / r[TARGET].var()  # ambos pandas (ddof=1): numpy usaria ddof=0 e enviesaria o R²
    r2_first = r[TARGET].corr(r[refs[0][0]]) ** 2
    gap = resid.rolling(RECENT).sum().dropna()
    act = pd.Series(y, index=r.index).rolling(RECENT).sum().iloc[-1] * 100
    exp = pd.Series(fit, index=r.index).rolling(RECENT).sum().iloc[-1] * 100
    z = (gap.iloc[-1] - gap.mean()) / gap.std() if len(gap) >= 30 and gap.std() > 0 else None

    names = ", ".join(lab for _, lab in refs)
    lines.append(
        f"Os referenciais ({names}) explicam {r2 * 100:.0f}% da variação diária do ativo"
        + (f"; {refs[0][1]} sozinho explica {r2_first * 100:.0f}%." if len(refs) > 1 else ".")
    )
    moves = " · ".join(
        f"{lab} {_pt(float(r[s].iloc[-RECENT:].sum() * 100), 1, True)}%" for s, lab in refs
    )
    if r2 < MIN_R2_FOR_GAP:
        lines.append(
            f"Os referenciais explicam pouco do ativo (R² < {MIN_R2_FOR_GAP * 100:.0f}%): "
            f"o descolamento de {RECENT} dias não é informativo."
        )
    elif z is not None:
        direction = "abaixo" if exp > act else "acima"
        lines.append(
            f"Últimos {RECENT} pregões (retornos somados): ativo {_pt(act, 1, True)}% · {moves}. O modelo esperava "
            f"{_pt(exp, 1, True)}%; o ativo ficou {abs(act - exp):.1f} pp {direction} do esperado "
            f"(z = {_pt(float(z), 2, True)}): {_z_text(float(z))}."
        )
    lines.append("Correlação não é causa, e a janela é curta (~2 anos, um único regime de mercado).")
    result.update(
        r2=_num(r2), r2_first=_num(r2_first), expected20_pp=_num(exp), actual20_pp=_num(act),
        gap20_pp=_num(act - exp), z20=_num(z) if z is not None else None,
    )
    return result


def _charts(closes: pd.DataFrame, refs: list[tuple[str, str]]) -> dict:
    out: dict = {"rebased": None, "rolling": None, "scatter": None}
    if not refs:
        return out
    cols = [TARGET] + [s for s, _ in refs]
    aligned = closes[cols].dropna()
    if len(aligned) < MIN_OBS + 1:
        return out
    names = {TARGET: "Ativo", **dict(refs)}

    tail = aligned.iloc[-REBASE_DAYS:]
    out["rebased"] = {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "series": {names[c]: [round(float(v), 2) for v in tail[c] / tail[c].iloc[0] * 100] for c in cols},
    }

    r = _returns(aligned)
    rolling_series: dict[str, list] = {}
    dates: list[str] = []
    for s, label in refs:
        roll = r[TARGET].rolling(ROLL).corr(r[s]).iloc[ROLL - 1 :]
        dates = [d.strftime("%Y-%m-%d") for d in roll.index]
        rolling_series[label] = [None if math.isnan(v) else round(float(v), 3) for v in roll]
    out["rolling"] = {"dates": dates, "series": rolling_series}

    s0, label0 = refs[0]
    x, y = r[s0].to_numpy() * 100, r[TARGET].to_numpy() * 100
    slope, intercept = np.polyfit(x, y, 1)
    pts = [[round(float(a), 3), round(float(b), 3)] for a, b in zip(x, y)]
    out["scatter"] = {
        "ref": label0, "points": pts[:-RECENT], "recent": pts[-RECENT:],
        "slope": float(slope), "intercept": float(intercept),
    }
    return out


def build_panel(
    closes: pd.DataFrame,
    candidates: list[Instrument],
    fixed: list[tuple[str, str]],
    is_mechanical: Callable[[str], bool],
    exclude: set[str] | frozenset[str] = frozenset(),
) -> dict:
    fixed_rows: list[dict] = []
    for sym, label in fixed:
        if sym in exclude:
            continue
        mech = is_mechanical(sym)
        row = pair_row(closes, sym)
        base = {"symbol": sym, "label": label, "mechanical": mech}
        if row is None:
            fixed_rows.append({**base, "status": "sem dados", "n": 0})
        else:
            fixed_rows.append({**base, **row, "status": classify(row, mech)})

    fixed_syms = {s for s, _ in fixed}
    groups: dict[str, list[dict]] = {}
    for inst in candidates:
        if inst.symbol in fixed_syms or inst.symbol in exclude:
            continue
        row = pair_row(closes, inst.symbol)
        if row is None:
            continue
        mech = is_mechanical(inst.symbol)
        groups.setdefault(inst.group, []).append(
            {"symbol": inst.symbol, "label": inst.label, "mechanical": mech, **row, "status": classify(row, mech)}
        )
    discovered = [
        {"name": g, "items": sorted(items, key=lambda x: -abs(x["corr_full"]))[:TOP_PER_GROUP]}
        for g, items in groups.items()
    ]

    refs = [
        (r["symbol"], r["label"]) for r in fixed_rows if r["status"] not in ("mecânica", "sem dados")
    ]
    return {
        "fixed": fixed_rows,
        "discovered": discovered,
        "parecer": _parecer(closes, fixed_rows, refs) if fixed_rows else None,
        "charts": _charts(closes, refs),
    }
