"""Setups iniciais: as regras do scanner antigo (advanced_swing_scanner.py) em forma explícita e editável.

Diferenças em relação ao antigo, de propósito:
- sem score: cada condição aparece como bateu ou não bateu;
- o antigo usava RSI/MACD em H4: aqui cada regra existe nos dois timeframes, D1 (o nome original) e H4 (o mesmo nome com " (H4)");
- o antigo exigia "RSI + (MACD ou tendência)": aqui isso vira obrigatória + confirmações com mínimo.

O backtest feito antes mostrou que as regras antigas não superaram entradas aleatórias; os setups existem para o
usuário editar e para o diário medir, não como promessa.
"""
from __future__ import annotations

import copy

_FILTERS = {"min_price": 5, "min_dollar_volume": 20_000_000}  # só ações: preço > US$ 5 e liquidez mínima
_ALL = ["acoes", "cripto", "forex"]

DEFAULT_SETUPS: list[dict] = [
    {
        "name": "Recuperação de sobrevenda",
        "direction": "alta",
        "markets": _ALL,
        "enabled": True,
        "definition": {
            "required": [{"type": "rsi_cross_up", "params": {"level": 30}}],
            "confirmations": [
                {"type": "macd_above_signal", "params": {}},
                {"type": "trend_up", "params": {}},
                {"type": "volume_ratio_above", "params": {"x": 1.2}},
            ],
            "min_confirmations": 1,
            "filters": _FILTERS,
        },
    },
    {
        "name": "Pullback em tendência de alta",
        "direction": "alta",
        "markets": _ALL,
        "enabled": True,
        "definition": {
            "required": [
                {"type": "trend_up", "params": {}},
                {"type": "rsi_between", "params": {"lo": 50, "hi": 70}},
                {"type": "rsi_falling", "params": {}},
            ],
            "confirmations": [
                {"type": "macd_above_signal", "params": {}},
                {"type": "volume_ratio_above", "params": {"x": 1.2}},
            ],
            "min_confirmations": 0,
            "filters": _FILTERS,
        },
    },
    {
        "name": "Momentum em zona neutra",
        "direction": "alta",
        "markets": _ALL,
        "enabled": True,
        "definition": {
            "required": [
                {"type": "rsi_between", "params": {"lo": 40, "hi": 60}},
                {"type": "rsi_rising", "params": {}},
            ],
            "confirmations": [
                {"type": "macd_above_signal", "params": {}},
                {"type": "trend_up", "params": {}},
            ],
            "min_confirmations": 1,
            "filters": _FILTERS,
        },
    },
]


H4_SUFFIX = " (H4)"


def h4_variant(setup: dict) -> dict:
    """O mesmo setup em barras de 4 horas: mesmas condições, mesmos filtros, nome com o sufixo " (H4)"."""
    return {**copy.deepcopy(setup), "name": setup["name"] + H4_SUFFIX, "timeframe": "H4"}


DEFAULT_SETUPS_H4: list[dict] = [h4_variant(s) for s in DEFAULT_SETUPS]
