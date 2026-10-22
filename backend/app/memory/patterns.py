"""Alertas estatísticos calculados por código sobre o diário. A IA não participa.

Um alerta só existe quando uma diferença entre dois grupos de teses resolvidas é distinguível do acaso: ao menos
`MIN_N` resolvidas em cada lado e o intervalo de Newcombe da diferença fora do zero (as contas são as da aba Revisão).
Todo alerta mostra o número de casos dos dois lados. Como o app testa muitas comparações, o resultado traz também
quantas foram testadas e quantos "distinguíveis" o acaso sozinho produziria (≈ 5%): um alerta é indício para olhar os
casos e para ver se ele se repete em registros novos, nunca uma regra.
"""
from __future__ import annotations

from collections import Counter

from ..analysis.state_prob import wilson
from ..review import engine as review
from . import causes, similar

MIN_N = review.SMALL
CHANCE = 0.05  # taxa de falsos "distinguíveis" esperada por comparação, com intervalo de 95%


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _pp(x: float) -> str:
    return f"{x:+.0f} pp".replace("-", "−")


def _side(label: str, c: dict) -> str:
    return f"{label}: {c['alvo']} de {c['fechadas']} bateram o alvo ({_pct(c['taxa_acerto'])})"


def _alert(kind: str, key: str, title: str, a: dict, b: dict, a_label: str, b_label: str, diff: dict) -> dict:
    better = diff["leitura"] == "a_maior"
    lo, hi = diff["ic95_pp"]
    text = (
        f"{_side(a_label, a)}; {_side(b_label, b)}. Diferença {_pp(diff['pp'])} (IC95 {lo:+.0f} a {hi:+.0f} pp)".replace("-", "−")
        + f", n = {a['fechadas'] + b['fechadas']}."
    )
    return {
        "id": f"{kind}:{key}",
        "tipo": kind,
        "chave": key,
        "titulo": title,
        "texto": text,
        "sentido": "melhor" if better else "pior",  # do primeiro grupo em relação ao segundo
        "n": a["fechadas"] + b["fechadas"],
        "grupo": {"rotulo": a_label, **{k: a[k] for k in ("alvo", "invalidada", "fechadas", "taxa_acerto", "ic95", "ids")}},
        "contra": {"rotulo": b_label, **{k: b[k] for k in ("alvo", "invalidada", "fechadas", "taxa_acerto", "ic95", "ids")}},
        "diferenca_pp": diff["pp"],
        "ic95_pp": diff["ic95_pp"],
    }


def _compare(kind: str, key: str, title: str, group: list[dict], rest: list[dict], a_label: str, b_label: str):
    """(alerta ou None, se a comparação pôde ser testada)."""
    a, b = review.cell(group), review.cell(rest)
    diff = review.difference(a, b)
    tested = diff["leitura"] != "sem dados"
    if diff["leitura"] not in ("a_maior", "b_maior"):
        return None, tested
    return _alert(kind, key, title, a, b, a_label, b_label, diff), tested


def _from_concordance(kind: str, key: str, title: str, conc: dict, a_label: str, b_label: str):
    diff = conc["diferenca"]
    tested = diff["leitura"] != "sem dados"
    if diff["leitura"] not in ("a_maior", "b_maior"):
        return None, tested
    return _alert(kind, key, title, conc["a_favor"], conc["contra"], a_label, b_label, diff), tested


def global_alerts(entries: list[dict]) -> dict:
    rows = list(entries)
    alerts: list[dict] = []
    tested = 0
    seen: set[tuple] = set()

    def take(res) -> None:
        nonlocal tested
        alert, was_tested = res
        tested += was_tested
        if not alert:
            return
        # "grupo contra o resto" gera o espelho quando o resto é outro grupo (dois setups, dois mercados): um alerta só
        pair = (alert["tipo"], frozenset(alert["grupo"]["ids"]), frozenset(alert["contra"]["ids"]))
        if (pair[0], pair[2], pair[1]) in seen:
            return
        seen.add(pair)
        alerts.append(alert)

    for name in sorted({n for r in rows for n in similar.setups_of(r)}):
        has = [r for r in rows if name in similar.setups_of(r)]
        rest = [r for r in rows if name not in similar.setups_of(r)]
        take(_compare("setup", name, f"Setup \"{name}\"", has, rest, "neste setup", "no resto do diário"))
    for market in sorted({r["market"] for r in rows}):
        take(_compare("mercado", market, f"Mercado: {market}", [r for r in rows if r["market"] == market],
                      [r for r in rows if r["market"] != market], "neste mercado", "nos outros mercados"))

    entered = [r for r in rows if r["decision"] == "entrei"]
    skipped = [r for r in rows if r["decision"] != "entrei"]
    take(_compare("decisao", "entrei", "Teses em que você entrou × as que deixou de fora", entered, skipped,
                  "entrou", "ficou de fora"))
    early = [r for r in entered if r["early_exit_at"]]
    kept = [r for r in entered if not r["early_exit_at"]]
    take(_compare("saida_antecipada", "saida_antecipada", "Depois de uma saída antecipada, a tese seguiu em frente?",
                  early, kept, "saiu antes", "manteve até o fim"))

    for b in review.by_block(rows):
        take(_from_concordance("bloco", b["bloco"], f"Bloco: {b['titulo']}", b, "bloco concordava", "bloco discordava"))
    for lens in review.by_lens(rows)["lentes"]:
        take(_from_concordance("lente", lens["lente"], f"Lente de IA: {lens['lente']}", lens, "lente concordava", "lente discordava"))

    alerts.sort(key=lambda a: -abs(a["diferenca_pp"]))
    resolved = review.cell(rows)
    return {
        "alertas": alerts,
        "testadas": tested,
        "distinguiveis": len(alerts),
        "esperados_por_acaso": round(CHANCE * tested, 1),
        "minimo_por_grupo": MIN_N,
        "registros": len(rows),
        "resolvidas": resolved["fechadas"],
    }


def cause_distribution(postmortems: dict[int, dict]) -> dict:
    """Quantas vezes cada causa foi apontada pela IA nos pós-mortems. É classificação da IA, não medida."""
    n = len(postmortems)
    counts = Counter(pm["result"]["causa_principal"] for pm in postmortems.values())
    items = []
    for cause in causes.CAUSES:
        c = counts[cause.id]
        if c:
            lo, hi = wilson(c, n)
            items.append({"causa": cause.id, "titulo": cause.title, "n": c, "taxa": c / n, "ic95": [lo, hi]})
    items.sort(key=lambda i: -i["n"])
    seen = Counter(pm["result"]["visibilidade"] for pm in postmortems.values())
    return {
        "n": n,
        "amostra": review.sample_label(n),
        "itens": items,
        "visibilidade": dict(seen),
        "nota": "Causa atribuída por IA (hipótese), não medida pelo código. Com poucos casos é indício, não regra.",
    }


def asset_memory(
    entries: list[dict], postmortems: dict[int, dict], market: str, symbol: str, stances: dict, setups: list[str],
    direction: str | None = None,
) -> dict:
    """O que o diário sabe sobre o estado atual de um ativo: histórico dele, dos setups, casos parecidos e alertas que se aplicam."""
    same = [r for r in entries if r["market"] == market and r["symbol"] == symbol]
    found = similar.find(
        {"market": market, "symbol": symbol, "stances": stances, "setups": setups, "direction": direction}, entries, postmortems
    )
    glob = global_alerts(entries)
    informative = {k for k, v in stances.items() if v in ("alta", "baixa")}
    applicable = [
        a for a in glob["alertas"]
        if a["tipo"] in ("decisao", "saida_antecipada")
        or (a["tipo"] == "setup" and a["chave"] in setups)
        or (a["tipo"] == "mercado" and a["chave"] == market)
        or (a["tipo"] == "bloco" and a["chave"] in informative)
    ]
    return {
        "historico_do_ativo": review.cell(same),
        "setups": [{"setup": s, **review.cell([r for r in entries if s in similar.setups_of(r)])} for s in setups],
        "parecidos": found,
        "alertas_aplicaveis": applicable,
        "comparacoes": {k: glob[k] for k in ("testadas", "distinguiveis", "esperados_por_acaso", "minimo_por_grupo")},
    }
