"""Inclinação probabilística: P(alta em N dias | estado atual), com amostra, intervalo e base.

Não é sinal de compra/venda. Para o estado atual do ativo, conta quantas vezes (sem sobreposição)
o mesmo estado ocorreu no histórico e em quantas o preço estava mais alto N barras depois, e compara
com a base do próprio ativo (probabilidade de alta sem condição nenhuma).

Limites: intervalo de Wilson assume observações independentes; um único ativo tem amostra pequena.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .indicators import add_indicators

MIN_N = 30
RSI_LOW, RSI_HIGH = 35.0, 65.0

_RSI_TEXT = {
    "baixo": f"RSI baixo (<{RSI_LOW:g})",
    "neutro": f"RSI neutro ({RSI_LOW:g}–{RSI_HIGH:g})",
    "alto": f"RSI alto (>{RSI_HIGH:g})",
}
_MACD_TEXT = {"acima": "MACD acima do sinal", "abaixo": "MACD abaixo do sinal"}
_TREND_TEXT = {True: "tendência de alta (preço > MM20 > MM50)", False: "sem tendência de alta"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - a) / d, (c + a) / d)


def describe(rsi_zone: str, macd_pos: str, uptrend: bool) -> str:
    return " · ".join([_RSI_TEXT[rsi_zone], _MACD_TEXT[macd_pos], _TREND_TEXT[bool(uptrend)]])


def sample_non_overlapping(positions: np.ndarray, horizon: int) -> list[int]:
    """Escolhe ocorrências com pelo menos `horizon` barras de distância (janelas não se sobrepõem)."""
    picked: list[int] = []
    last = -(10**9)
    for p in positions:
        if p - last >= horizon:
            picked.append(int(p))
            last = int(p)
    return picked


def _build_states(d: pd.DataFrame) -> pd.DataFrame:
    valid = d[["rsi14", "macd", "macd_signal", "sma20", "sma50"]].notna().all(axis=1).to_numpy()
    rsi_zone = np.select([d["rsi14"] < RSI_LOW, d["rsi14"] > RSI_HIGH], ["baixo", "alto"], default="neutro")
    macd_pos = np.where(d["macd"] > d["macd_signal"], "acima", "abaixo")
    uptrend = ((d["Close"] > d["sma20"]) & (d["sma20"] > d["sma50"])).to_numpy()
    st = pd.DataFrame({"rsi": rsi_zone, "macd": macd_pos, "uptrend": uptrend}, index=d.index)
    return st[valid]


def _stats(positions: np.ndarray, up: np.ndarray, horizon: int, base: float) -> dict:
    picked = sample_non_overlapping(positions, horizon)
    n = len(picked)
    k = int(up[picked].sum()) if n else 0
    p = k / n if n else None
    if n < MIN_N:
        return {"n": n, "p_up": p, "ci": None, "lift_pp": None, "label": "sem dados"}
    lo, hi = wilson(k, n)
    label = "alta" if lo > base else "baixa" if hi < base else "indistinta"
    return {"n": n, "p_up": p, "ci": [lo, hi], "lift_pp": (p - base) * 100, "label": label}


def _reason(label: str, n: int) -> str:
    if label == "sem dados":
        return f"Só {n} ocorrências sem sobreposição deste estado (mínimo {MIN_N}): não dá para estimar."
    if label == "indistinta":
        return "O intervalo de confiança inclui a base do ativo: sem inclinação distinguível."
    side = "acima" if label == "alta" else "abaixo"
    return (
        f"O intervalo de confiança está {side} da base do ativo. Com vários estados testados, parte dos "
        "resultados 'distinguíveis' é acaso: valide no diário antes de confiar."
    )


def conditional_probability(df: pd.DataFrame, horizon: int = 10) -> dict:
    d = add_indicators(df)
    st = _build_states(d)
    out: dict = {
        "horizon_days": horizon,
        "min_n": MIN_N,
        "state": None,
        "state_label": None,
        "n": 0,
        "p_up": None,
        "ci": None,
        "base": None,
        "lift_pp": None,
        "label": "sem dados",
        "reason": "",
        "history_bars": int(len(st)),
        "history_start": st.index[0].date().isoformat() if len(st) else None,
        "all_states": [],
    }
    if st.empty or st.index[-1] != d.index[-1]:
        out["reason"] = "Histórico curto demais para calcular os indicadores do estado atual."
        return out

    future = d["Close"].shift(-horizon)
    has_future = future.notna().to_numpy()
    up = (future > d["Close"]).to_numpy()
    pos_all = d.index.get_indexer(st.index)
    usable = has_future[pos_all]
    if usable.sum() == 0:
        out["reason"] = "Histórico curto demais para medir o que aconteceu depois."
        return out
    base = float(up[pos_all][usable].mean())
    out["base"] = base

    cur = st.iloc[-1]
    cur_key = (cur["rsi"], cur["macd"], bool(cur["uptrend"]))
    out["state"] = {"rsi": cur_key[0], "macd": cur_key[1], "uptrend": cur_key[2]}
    out["state_label"] = describe(*cur_key)

    rows = []
    for key, grp in st.groupby(["rsi", "macd", "uptrend"]):
        key = (key[0], key[1], bool(key[2]))
        mask = np.isin(st.index, grp.index) & usable
        stats = _stats(pos_all[mask], up, horizon, base)
        rows.append({"state_label": describe(*key), "is_current": key == cur_key, **stats})
    rows.sort(key=lambda r: -r["n"])
    out["all_states"] = rows

    current = next(r for r in rows if r["is_current"]) if any(r["is_current"] for r in rows) else None
    if current is None:  # estado atual ainda sem nenhuma ocorrência passada com desfecho
        current = {"n": 0, "p_up": None, "ci": None, "lift_pp": None, "label": "sem dados"}
    out.update({k: current[k] for k in ("n", "p_up", "ci", "lift_pp", "label")})
    out["reason"] = _reason(out["label"], out["n"])
    return out
