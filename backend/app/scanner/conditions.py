"""Catálogo de condições dos setups. Cada condição olha a última barra diária fechada (e a anterior).

`fn(d, p)` recebe o DataFrame de features (ver engine.features) e os parâmetros; devolve True/False, ou None
quando falta dado (ex.: indicador ainda sem histórico). Condições que dependem de volume são "não aplicáveis"
em mercados sem volume (forex): ficam de fora, em vez de reprovar o ativo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    default: float
    step: float = 1.0
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Condition:
    id: str
    title: str  # nome no catálogo
    label: str  # texto exibido, com {parâmetros}
    fn: Callable[[pd.DataFrame, dict], bool | None]
    params: tuple[Param, ...] = field(default_factory=tuple)
    needs_volume: bool = False

    def render(self, p: dict) -> str:
        return self.label.format(**{k: _fmt(v) for k, v in p.items()})


def _fmt(v: float) -> str:
    return f"{v:g}"


def _v(d: pd.DataFrame, col: str, back: int = 0) -> float | None:
    if len(d) <= back:
        return None
    x = d[col].iloc[-1 - back]
    return None if pd.isna(x) else float(x)


def _all(*xs) -> bool:
    return all(x is not None for x in xs)


def rsi_between(d, p):
    r = _v(d, "rsi14")
    return None if r is None else p["lo"] <= r <= p["hi"]


def rsi_cross_up(d, p):
    now, prev = _v(d, "rsi14"), _v(d, "rsi14", 1)
    return None if not _all(now, prev) else prev <= p["level"] < now


def rsi_cross_down(d, p):
    now, prev = _v(d, "rsi14"), _v(d, "rsi14", 1)
    return None if not _all(now, prev) else prev >= p["level"] > now


def rsi_rising(d, p):
    now, prev = _v(d, "rsi14"), _v(d, "rsi14", 1)
    return None if not _all(now, prev) else now > prev


def rsi_falling(d, p):
    now, prev = _v(d, "rsi14"), _v(d, "rsi14", 1)
    return None if not _all(now, prev) else now < prev


def macd_above_signal(d, p):
    m, s = _v(d, "macd"), _v(d, "macd_signal")
    return None if not _all(m, s) else m > s


def macd_below_signal(d, p):
    m, s = _v(d, "macd"), _v(d, "macd_signal")
    return None if not _all(m, s) else m < s


def macd_cross_up(d, p):
    m0, s0, m1, s1 = _v(d, "macd"), _v(d, "macd_signal"), _v(d, "macd", 1), _v(d, "macd_signal", 1)
    return None if not _all(m0, s0, m1, s1) else (m0 > s0 and m1 <= s1)


def macd_cross_down(d, p):
    m0, s0, m1, s1 = _v(d, "macd"), _v(d, "macd_signal"), _v(d, "macd", 1), _v(d, "macd_signal", 1)
    return None if not _all(m0, s0, m1, s1) else (m0 < s0 and m1 >= s1)


def macd_hist_rising(d, p):
    h0, h1 = _v(d, "macd_hist"), _v(d, "macd_hist", 1)
    return None if not _all(h0, h1) else h0 > h1


def trend_up(d, p):
    c, a, b = _v(d, "Close"), _v(d, "sma20"), _v(d, "sma50")
    return None if not _all(c, a, b) else c > a > b


def trend_down(d, p):
    c, a, b = _v(d, "Close"), _v(d, "sma20"), _v(d, "sma50")
    return None if not _all(c, a, b) else c < a < b


def _sma(d: pd.DataFrame, n: int) -> float | None:
    n = int(n)
    if len(d) < n:
        return None
    return float(d["Close"].iloc[-n:].mean())


def close_above_sma(d, p):
    c, s = _v(d, "Close"), _sma(d, p["n"])
    return None if not _all(c, s) else c > s


def close_below_sma(d, p):
    c, s = _v(d, "Close"), _sma(d, p["n"])
    return None if not _all(c, s) else c < s


def volume_ratio_above(d, p):
    r = _v(d, "vol_ratio")
    return None if r is None else r > p["x"]


def bb_pctb_between(d, p):
    b = _v(d, "bb_pctb")
    return None if b is None else p["lo"] <= b <= p["hi"]


def atr_pct_between(d, p):
    a = _v(d, "atr_pct")
    return None if a is None else p["lo"] <= a <= p["hi"]


def near_high(d, p):
    n = int(p["lookback"])
    if len(d) < n:
        return None
    hi, c = float(d["High"].iloc[-n:].max()), _v(d, "Close")
    return None if c is None else c >= hi * (1 - p["within_pct"] / 100)


def pullback_from_high(d, p):
    n = int(p["lookback"])
    if len(d) < n:
        return None
    hi, c = float(d["High"].iloc[-n:].max()), _v(d, "Close")
    if c is None or hi <= 0:
        return None
    return p["min_pct"] <= (hi - c) / hi * 100 <= p["max_pct"]


def up_day(d, p):
    c, prev = _v(d, "Close"), _v(d, "Close", 1)
    return None if not _all(c, prev) else c > prev


def down_day(d, p):
    c, prev = _v(d, "Close"), _v(d, "Close", 1)
    return None if not _all(c, prev) else c < prev


_LEVEL = Param("level", "nível", 30, 1, 0, 100)
_LO100 = Param("lo", "mín.", 40, 1, 0, 100)
_HI100 = Param("hi", "máx.", 60, 1, 0, 100)
_N = Param("n", "período", 50, 1, 2, 400)

CONDITIONS: list[Condition] = [
    Condition("rsi_between", "RSI entre", "RSI(14) entre {lo} e {hi}", rsi_between, (_LO100, _HI100)),
    Condition("rsi_cross_up", "RSI cruza para cima", "RSI(14) cruzou {level} para cima", rsi_cross_up, (_LEVEL,)),
    Condition("rsi_cross_down", "RSI cruza para baixo", "RSI(14) cruzou {level} para baixo", rsi_cross_down, (_LEVEL,)),
    Condition("rsi_rising", "RSI subindo", "RSI subindo (hoje > ontem)", rsi_rising),
    Condition("rsi_falling", "RSI caindo", "RSI caindo (hoje < ontem)", rsi_falling),
    Condition("macd_above_signal", "MACD acima do sinal", "MACD acima da linha de sinal", macd_above_signal),
    Condition("macd_below_signal", "MACD abaixo do sinal", "MACD abaixo da linha de sinal", macd_below_signal),
    Condition("macd_cross_up", "MACD cruza para cima", "MACD cruzou o sinal para cima hoje", macd_cross_up),
    Condition("macd_cross_down", "MACD cruza para baixo", "MACD cruzou o sinal para baixo hoje", macd_cross_down),
    Condition("macd_hist_rising", "Histograma do MACD subindo", "Histograma do MACD subindo", macd_hist_rising),
    Condition("trend_up", "Tendência de alta", "Tendência de alta (preço > MM20 > MM50)", trend_up),
    Condition("trend_down", "Tendência de baixa", "Tendência de baixa (preço < MM20 < MM50)", trend_down),
    Condition("close_above_sma", "Preço acima da média", "Preço acima da MM{n}", close_above_sma, (_N,)),
    Condition("close_below_sma", "Preço abaixo da média", "Preço abaixo da MM{n}", close_below_sma, (_N,)),
    Condition(
        "volume_ratio_above", "Volume acima da média", "Volume > {x}× a média de 20 dias", volume_ratio_above,
        (Param("x", "múltiplo", 1.2, 0.1, 0.1, 20),), needs_volume=True,
    ),
    Condition(
        "bb_pctb_between", "Bollinger %B entre", "Bollinger %B entre {lo} e {hi}", bb_pctb_between,
        (Param("lo", "mín.", 0.0, 0.05), Param("hi", "máx.", 0.5, 0.05)),
    ),
    Condition(
        "atr_pct_between", "Volatilidade (ATR%) entre", "ATR entre {lo}% e {hi}% do preço", atr_pct_between,
        (Param("lo", "mín. (%)", 0.5, 0.1, 0), Param("hi", "máx. (%)", 6, 0.1, 0)),
    ),
    Condition(
        "near_high", "Perto da máxima", "Preço a até {within_pct}% da máxima de {lookback} dias", near_high,
        (Param("lookback", "dias", 252, 1, 5, 500), Param("within_pct", "até (%)", 5, 0.5, 0, 100)),
    ),
    Condition(
        "pullback_from_high", "Recuo desde a máxima", "Recuo de {min_pct}% a {max_pct}% desde a máxima de {lookback} dias",
        pullback_from_high,
        (Param("lookback", "dias", 20, 1, 5, 500), Param("min_pct", "mín. (%)", 3, 0.5, 0), Param("max_pct", "máx. (%)", 10, 0.5, 0)),
    ),
    Condition("up_day", "Dia de alta", "Fechou em alta (hoje > ontem)", up_day),
    Condition("down_day", "Dia de baixa", "Fechou em baixa (hoje < ontem)", down_day),
]

CATALOG: dict[str, Condition] = {c.id: c for c in CONDITIONS}


def catalog_payload() -> list[dict]:
    return [
        {
            "id": c.id,
            "title": c.title,
            "needs_volume": c.needs_volume,
            "params": [
                {"name": p.name, "label": p.label, "default": p.default, "step": p.step, "min": p.min, "max": p.max}
                for p in c.params
            ],
        }
        for c in CONDITIONS
    ]


def normalize_condition(raw: dict) -> dict:
    """Valida o tipo e completa os parâmetros que faltam com o padrão do catálogo."""
    ctype = raw.get("type")
    spec = CATALOG.get(ctype)
    if spec is None:
        raise ValueError(f"Condição desconhecida: {ctype!r}")
    params = {}
    given = raw.get("params") or {}
    for p in spec.params:
        value = given.get(p.name, p.default)
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parâmetro {p.name!r} de {ctype!r} precisa ser numérico") from exc
        if (p.min is not None and value < p.min) or (p.max is not None and value > p.max):
            raise ValueError(f"Parâmetro {p.name!r} de {ctype!r} fora do intervalo [{p.min}, {p.max}]")
        params[p.name] = value
    return {"type": ctype, "params": params}


def normalize_definition(defn: dict) -> dict:
    required = [normalize_condition(c) for c in defn.get("required", [])]
    confirmations = [normalize_condition(c) for c in defn.get("confirmations", [])]
    if not required and not confirmations:
        raise ValueError("O setup precisa de pelo menos uma condição.")
    min_conf = int(defn.get("min_confirmations", 0))
    if min_conf < 0 or min_conf > len(confirmations):
        raise ValueError("min_confirmations deve estar entre 0 e o número de confirmações.")
    if not required and min_conf == 0:
        raise ValueError("Sem condições obrigatórias, exija pelo menos 1 confirmação.")
    filters = defn.get("filters") or {}
    return {
        "required": required,
        "confirmations": confirmations,
        "min_confirmations": min_conf,
        "filters": {
            "min_price": float(filters.get("min_price") or 0),
            "min_dollar_volume": float(filters.get("min_dollar_volume") or 0),
        },
    }
