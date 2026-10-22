"""A memória que entra na análise com IA (prompt v2): casos parecidos e estatísticas, tudo calculado por código.

Privacidade: o que sai do computador por esta via é estruturado e sem texto livre. Cada caso leva mercado, ativo, direção,
mês do registro, desfecho, prazo, os motivos da semelhança, o que a lente dizia na época e, se houver, a causa do pós-mortem.
Nunca vão a tese, as notas, o motivo de saída, a decisão (entrei ou não), nem os preços do plano.

Isolamento das lentes: cada lente recebe, nos casos, só o que ELA mesma disse (`sua_lente_dizia`), nunca o que as outras disseram.
"""
from __future__ import annotations

import json

from ..review import blocks, engine as review
from . import similar

MEMORY_CASES = 5

DESCRIPTION = (
    "Casos anteriores do diário do operador cujo estado se parece com o atual (escolhidos por código, com os motivos), e "
    "estatísticas sobre eles. \"desfecho\": alvo = a tese bateu o alvo antes da invalidação; invalidada = o contrário; "
    "expirada = nenhum dos dois no horizonte. \"pos_mortem.causa\" foi classificada por outra IA e é hipótese, não medida. "
    "Poucos casos são indício, não regra."
)

# Mapas do pacote da análise (português) para o formato do snapshot do diário, que é o que `blocks.derive` lê.
_PROB = {"alta": "alta", "baixa": "baixa", "indistinta": "indistinta", "sem_dados": "sem dados"}
_REFS = {"sp500": "^GSPC", "dxy": "DX-Y.NYB"}


def snapshot_from_package(pkg: dict) -> dict:
    """Reconstrói, do pacote da análise, o mesmo snapshot que o diário guarda no registro."""
    fatias = pkg.get("fatias") or {}
    ind = fatias.get("indicadores") or {}
    values = ind.get("valores") or {}
    prob = ind.get("probabilidade") or {}
    pa = fatias.get("price_action") or {}
    corr = fatias.get("correlacao") or {}
    snap: dict = {}
    if values:
        snap["indicators"] = {k: values.get(k) for k in ("trend", "macd_hist", "rsi14", "close", "sma20", "atr14")}
    if prob:
        snap["probability"] = {"label": _PROB.get(prob.get("rotulo"), "sem dados")}
    if pa:
        snap["price_action"] = {"estrutura": pa.get("estrutura")}
    refs = corr.get("referencias_fixas") if corr.get("disponivel") else None
    if refs:
        snap["correlation"] = {
            _REFS[slug]: {k: ref.get(k) for k in ("status", "corr_full", "move20_other", "other_unit")}
            for slug, ref in refs.items()
            if slug in _REFS and isinstance(ref, dict)
        }
    return snap


def _month(ts: str) -> str:
    return ts[:7]


def _stat(description: str, c: dict) -> dict:
    return {
        "descricao": description, "n": c["fechadas"], "alvo": c["alvo"], "invalidada": c["invalidada"],
        "taxa_acerto": None if c["taxa_acerto"] is None else round(c["taxa_acerto"], 3),
        "ic95": None if c["ic95"] is None else [round(x, 3) for x in c["ic95"]],
    }


def build(pkg: dict, entries: list[dict], postmortems: dict[int, dict]) -> dict:
    """A fatia `memoria` do pacote (completa; `for_lens` recorta para cada lente)."""
    market, symbol = pkg["ativo"]["mercado"], pkg["ativo"]["simbolo"]
    snap = snapshot_from_package(pkg)
    stances = blocks.derive(snap)
    if not any(r["status"] != "aberta" for r in entries):
        return {"disponivel": False, "motivo": "O diário ainda não tem casos resolvidos."}
    found = similar.find({"market": market, "symbol": symbol, "stances": stances}, entries, postmortems, k=MEMORY_CASES)
    if not found["total_parecidos"]:
        return {
            "disponivel": True,
            "descricao": DESCRIPTION,
            "estado_atual_dos_blocos": {k: v for k, v in stances.items() if v is not None},
            "casos": [],
            "estatisticas": [],
            "avisos": [f"Nenhum caso resolvido do diário passa do corte de semelhança ({similar.MIN_SCORE} pontos)."],
        }

    by_id = {r["id"]: r for r in entries}
    lens_by_case = {c["id"]: past_lenses(by_id[c["id"]]) for c in found["casos"]}
    cases = []
    for c in found["casos"]:
        cases.append(
            {
                "mercado": c["mercado"], "simbolo": c["simbolo"], "direcao": c["direcao"],
                "registrado_em": _month(c["registrado_em"]), "desfecho": c["desfecho"],
                "dias_ate_desfecho": c["dias_ate_desfecho"], "por_que_parecido": c["por_que_parecido"],
                "pos_mortem": c["pos_mortem"],
                "_lentes": lens_by_case[c["id"]],  # recortado por `for_lens` e removido antes de sair
            }
        )
    g = found["grupo"]
    stats = [
        _stat(f"todas as teses de casos parecidos (de {found['total_parecidos']} que passam do corte)", g["todos"]),
        _stat("teses de alta em casos parecidos", g["teses_de_alta"]),
        _stat("teses de baixa em casos parecidos", g["teses_de_baixa"]),
    ]
    same = [r for r in entries if r["market"] == market and r["symbol"] == symbol and r["status"] != "aberta"]
    if same:
        stats.append(_stat("teses neste mesmo ativo (qualquer estado)", review.cell(same)))
    notes = []
    if found["total_parecidos"] < 10:
        notes.append(f"Poucos casos parecidos ({found['total_parecidos']}): leia como indício, não como regra.")
    return {
        "disponivel": True,
        "descricao": DESCRIPTION,
        "estado_atual_dos_blocos": {k: v for k, v in stances.items() if v is not None},
        "casos": cases,
        "estatisticas": stats,
        "avisos": notes,
    }


def past_lenses(row: dict) -> dict:
    """Inclinação e confiança que cada lente de IA deu naquele caso (lente -> {inclinacao, confianca})."""
    try:
        snap = json.loads(row.get("snapshot_json") or "{}")
        lenses = ((snap.get("ai") or {}).get("lenses")) or {}
    except (TypeError, ValueError):
        return {}
    return {
        name: {"inclinacao": v.get("inclinacao"), "confianca": v.get("confianca")}
        for name, v in lenses.items()
        if isinstance(v, dict)
    }


def for_lens(memory: dict, lens_id: str) -> dict:
    """A memória como UMA lente a vê: nos casos, só a própria resposta passada dela."""
    out = {k: v for k, v in memory.items() if k != "casos"}
    cases = []
    for c in memory.get("casos", []):
        own = (c.get("_lentes") or {}).get(lens_id)
        cases.append({**{k: v for k, v in c.items() if k != "_lentes"}, "sua_lente_dizia": own})
    if "casos" in memory:
        out["casos"] = cases
    return out
