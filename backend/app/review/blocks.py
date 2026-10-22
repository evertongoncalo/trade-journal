"""Inclinação de cada bloco de código, lida do snapshot que o diário guardou no momento do registro.

A leitura é feita na revisão, a partir dos valores brutos gravados (não de rótulos congelados), e a versão das regras
aparece na tela: mudar uma regra exige subir `RULES_VERSION`. Cada regra olha UM bloco; nada é somado num score.

Inclinações: "alta", "baixa", "indistinta" (o bloco olhou e não aponta lado) ou "sem_dados" (não conseguiu olhar).
`None` = o registro não guardou o bloco (registro antigo) ou ele não se aplica ao ativo.
"""
from __future__ import annotations

RULES_VERSION = "blocos-v1"

# (chave, título, regra em palavras)
BLOCKS: list[tuple[str, str, str]] = [
    ("probabilidade", "Inclinação probabilística", "Rótulo da ficha: P(alta em N dias | estado) acima ou abaixo da base do ativo, com amostra mínima."),
    ("tendencia", "Tendência (médias)", "Alta: preço > MM20 > MM50. Baixa: preço < MM20 < MM50. Lateral = sem inclinação."),
    ("macd", "MACD", "Alta: histograma (MACD − sinal) acima de zero. Baixa: abaixo de zero."),
    ("price_action", "Price action (estrutura)", "Alta: topos e fundos ascendentes. Baixa: descendentes. Misto = sem inclinação."),
    ("corr_sp500", "Correlação com o S&P 500", "Com relação estável: o sinal da correlação × o movimento de 20 dias do S&P 500 indica o lado."),
    ("corr_dxy", "Correlação com o DXY", "Com relação estável: o sinal da correlação × o movimento de 20 dias do DXY indica o lado."),
]
BLOCK_TITLE = {k: t for k, t, _ in BLOCKS}

_PROB = {"alta": "alta", "baixa": "baixa", "indistinta": "indistinta", "sem dados": "sem_dados"}
_TREND = {"alta": "alta", "baixa": "baixa", "lateral": "indistinta", "indefinida": "sem_dados"}
_STRUCTURE = {
    "topos e fundos ascendentes": "alta",
    "topos e fundos descendentes": "baixa",
    "indefinida": "sem_dados",
}
# Os mesmos limites do painel de correlação para um movimento "desprezível" (engine.pair_row).
_TINY_MOVE = {"%": 0.5, "pts": 0.05}
_CORR_REFS = {"corr_sp500": "^GSPC", "corr_dxy": "DX-Y.NYB"}


def _get(d, *path):
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d


def _probabilidade(snap: dict) -> str | None:
    label = _get(snap, "probability", "label")
    return None if label is None else _PROB.get(label, "sem_dados")


def _tendencia(snap: dict) -> str | None:
    trend = _get(snap, "indicators", "trend")
    return None if trend is None else _TREND.get(trend, "sem_dados")


def _macd(snap: dict) -> str | None:
    if "indicators" not in snap:
        return None
    hist = _get(snap, "indicators", "macd_hist")
    if hist is None:
        return "sem_dados"
    return "alta" if hist > 0 else "baixa" if hist < 0 else "indistinta"


def _price_action(snap: dict) -> str | None:
    structure = _get(snap, "price_action", "estrutura")
    if structure is None:
        return None
    return _STRUCTURE.get(structure, "indistinta")  # "misto (...)" cai aqui


def _corr(snap: dict, block: str) -> str | None:
    ref = _get(snap, "correlation", _CORR_REFS[block])
    if not isinstance(ref, dict):
        return None
    status = ref.get("status")
    if status == "mecânica":
        return None  # a relação é por construção (ex.: DXY × EURUSD): não diz nada independente
    if status == "sem dados":
        return "sem_dados"
    corr, move = ref.get("corr_full"), ref.get("move20_other")
    if status != "estável":
        return "indistinta"
    if corr is None or move is None:
        return "sem_dados"
    if abs(move) < _TINY_MOVE.get(ref.get("other_unit") or "%", 0.5):
        return "indistinta"
    return "alta" if (corr > 0) == (move > 0) else "baixa"


def derive(snap: dict) -> dict[str, str | None]:
    """Inclinação de cada bloco para um snapshot do diário."""
    return {
        "probabilidade": _probabilidade(snap),
        "tendencia": _tendencia(snap),
        "macd": _macd(snap),
        "price_action": _price_action(snap),
        "corr_sp500": _corr(snap, "corr_sp500"),
        "corr_dxy": _corr(snap, "corr_dxy"),
    }


_LENS_STANCE = {"para_alta": "alta", "para_baixa": "baixa", "indistinta": "indistinta", "sem_dados": "sem_dados"}


def ai_lenses(snap: dict) -> dict[str, str]:
    """Inclinação de cada lente da análise com IA que acompanhou o registro (lente -> inclinação)."""
    lenses = _get(snap, "ai", "lenses")
    if not isinstance(lenses, dict):
        return {}
    return {
        name: _LENS_STANCE.get(v.get("inclinacao"), "sem_dados")
        for name, v in lenses.items()
        if isinstance(v, dict)
    }
