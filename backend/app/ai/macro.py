"""Contexto macro (só código): variação recente de dólar, juros, risco, commodities e cripto.

Vem do universo de correlação já guardado (fechamentos alinhados às 16h de Nova York). A IA não busca nada:
se o universo não foi baixado, o pacote diz que o macro está indisponível e a lente responde "sem_dados".
"""
from __future__ import annotations

from ..correlation import store

# (chave no pacote, símbolo no Yahoo, nome, unidade da variação)
MACRO = [
    ("dxy", "DX-Y.NYB", "DXY (dólar)", "%"),
    ("sp500", "^GSPC", "S&P 500", "%"),
    ("nasdaq100", "^NDX", "Nasdaq 100", "%"),
    ("russell2000", "^RUT", "Russell 2000", "%"),
    ("vix", "^VIX", "VIX", "%"),
    ("juro10a", "^TNX", "Juro 10 anos dos EUA", "pts"),
    ("juro5a", "^FVX", "Juro 5 anos dos EUA", "pts"),
    ("treasuries_longos", "TLT", "Treasuries longos (TLT)", "%"),
    ("credito_high_yield", "HYG", "Crédito high yield (HYG)", "%"),
    ("ouro", "GC=F", "Ouro (futuro)", "%"),
    ("petroleo", "CL=F", "Petróleo WTI (futuro)", "%"),
    ("cobre", "HG=F", "Cobre (futuro)", "%"),
    ("bitcoin", "BTC-USD", "Bitcoin", "%"),
]
CRYPTO_KEYS = ("dxy", "sp500", "nasdaq100", "vix", "juro10a", "bitcoin")
WINDOWS = {"var_5d": 5, "var_20d": 20, "var_60d": 60}  # em observações (dias com pregão)


def _sig(x: float, digits: int = 5) -> float:
    return float(f"{x:.{digits}g}")


def snapshot(keys: tuple[str, ...] | None = None) -> dict:
    closes = store.load_closes()
    if closes.empty:
        return {"disponivel": False, "motivo": "O universo de correlação ainda não foi baixado (botão 'Atualizar universo')."}
    items: dict[str, dict] = {}
    latest = None
    for key, sym, name, unit in MACRO:
        if (keys and key not in keys) or sym not in closes.columns:
            continue
        s = closes[sym].dropna()
        if len(s) <= max(WINDOWS.values()):
            continue
        last = float(s.iloc[-1])
        item: dict = {"nome": name, "ultimo": _sig(last), "unidade_da_variacao": unit}
        for label, n in WINDOWS.items():
            base = float(s.iloc[-1 - n])
            item[label] = round(last - base, 3) if unit == "pts" else round((last / base - 1) * 100, 2) if base else None
        items[key] = item
        latest = s.index[-1] if latest is None or s.index[-1] > latest else latest
    if not items:
        return {"disponivel": False, "motivo": "Sem histórico suficiente no universo de correlação."}
    return {
        "disponivel": True,
        "ate": latest.date().isoformat(),
        "nota": "variações em % (juros em pontos), medidas em fechamentos alinhados às 16h de Nova York",
        "instrumentos": items,
    }
