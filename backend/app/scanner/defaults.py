"""Setups iniciais: as regras do scanner antigo (advanced_swing_scanner.py) em forma explícita e editável.

Diferenças em relação ao antigo, de propósito:
- sem score: cada condição aparece como bateu ou não bateu;
- timeframe diário (o antigo usava RSI/MACD em H4; H4 ainda não existe aqui);
- o antigo exigia "RSI + (MACD ou tendência)": aqui isso vira obrigatória + confirmações com mínimo.

O backtest feito antes mostrou que as regras antigas não superaram entradas aleatórias; os setups existem para o
usuário editar e para o diário medir, não como promessa.
"""
from __future__ import annotations

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
