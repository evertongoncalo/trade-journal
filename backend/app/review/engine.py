"""Revisão do acerto: recorta os registros do diário por mercado, setup, decisão, bloco de código e lente de IA.

"Acerto da tese" = alvo / (alvo + invalidada), o mesmo do diário. Expiradas e abertas ficam fora da taxa, mas aparecem.
Toda taxa vem com o n e o intervalo de Wilson; nada é somado num score. Para blocos e lentes a pergunta é:
"quando o bloco concordava com a minha tese, ela bateu o alvo mais do que quando discordava?" Se o bloco não soubesse
nada, as duas taxas seriam iguais; a diferença é medida com o intervalo de Newcombe.
"""
from __future__ import annotations

import json
import math
from collections import Counter

from ..analysis.state_prob import wilson
from . import blocks

SMALL = 10  # abaixo disso a taxa não diz nada
OK = 30  # a partir daqui a mesma régua do restante do app (inclinação probabilística)
DECISIONS = ("entrei", "nao_entrei", "observando")
RESPONSES = ("entrei", "ignorei", "observando")
ALERT_KINDS = ("avulso", "entrada", "invalidacao", "alvo")


def sample_label(n: int) -> str:
    return "insuficiente" if n < SMALL else "pequena" if n < OK else "ok"


def _snapshot(row: dict) -> dict:
    try:
        snap = json.loads(row.get("snapshot_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return snap if isinstance(snap, dict) else {}


def cell(rows: list[dict]) -> dict:
    """Contagem de desfechos de um grupo de registros e a taxa de acerto da tese."""
    counts = Counter(r["status"] for r in rows)
    hit, miss = counts["alvo"], counts["invalidada"]
    n = hit + miss
    interval = None
    if n:
        lo, hi = wilson(hit, n)
        interval = [lo, hi]
    return {
        "registros": len(rows),
        "alvo": hit,
        "invalidada": miss,
        "expirada": counts["expirada"],
        "aberta": counts["aberta"],
        "fechadas": n,
        "taxa_acerto": hit / n if n else None,
        "ic95": interval,
        "amostra": sample_label(n),
        "ids": sorted(r["id"] for r in rows),
    }


def rate(hits: int, n: int) -> dict:
    """Uma proporção qualquer com intervalo (usada onde "acerto" não é alvo/invalidada)."""
    interval = None
    if n:
        lo, hi = wilson(hits, n)
        interval = [lo, hi]
    return {"acertos": hits, "fechadas": n, "taxa": hits / n if n else None, "ic95": interval, "amostra": sample_label(n)}


def difference(a: dict, b: dict) -> dict:
    """Taxa de `a` menos taxa de `b` (em pontos percentuais) com o intervalo de Newcombe, e a leitura em palavras."""
    if not a["fechadas"] or not b["fechadas"]:
        return {"pp": None, "ic95_pp": None, "leitura": "sem dados"}
    pa, pb = a["taxa_acerto"], b["taxa_acerto"]
    (la, ua), (lb, ub) = a["ic95"], b["ic95"]
    d = pa - pb
    lo = d - math.sqrt((pa - la) ** 2 + (ub - pb) ** 2)
    hi = d + math.sqrt((ua - pa) ** 2 + (pb - lb) ** 2)
    if min(a["fechadas"], b["fechadas"]) < SMALL:
        reading = "sem dados"
    elif lo > 0:
        reading = "a_maior"  # o intervalo não inclui zero e favorece `a`
    elif hi < 0:
        reading = "b_maior"
    else:
        reading = "indistinta"
    return {"pp": d * 100, "ic95_pp": [lo * 100, hi * 100], "leitura": reading}


def _group(rows: list[dict], keys) -> list[dict]:
    """Agrupa; `keys(row)` devolve uma chave ou uma lista de chaves (o registro conta em cada uma)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        k = keys(r)
        for key in k if isinstance(k, (list, tuple)) else [k]:
            groups.setdefault(key, []).append(r)
    out = [{"chave": key, **cell(rs)} for key, rs in groups.items()]
    return sorted(out, key=lambda c: (-c["registros"], c["chave"]))


def _setup_names(row: dict) -> list[str]:
    names = [s.strip() for s in (row.get("setup") or "").split(" + ") if s.strip()]
    return names or ["(sem setup)"]


def _concordance(rows: list[dict], stance_of) -> dict:
    """Separa os registros pelo lado que o bloco apontava em relação à direção da tese.

    `stance_of(row)` devolve "alta", "baixa", "indistinta", "sem_dados" ou None (sem registro do bloco).
    """
    favor, contra, none, missing = [], [], [], 0
    for r in rows:
        stance = stance_of(r)
        if stance is None:
            missing += 1
        elif stance in ("alta", "baixa"):
            (favor if stance == r["direction"] else contra).append(r)
        else:
            none.append(r)
    a, c = cell(favor), cell(contra)
    return {
        "a_favor": a,
        "contra": c,
        "sem_inclinacao": cell(none),
        "sem_registro": missing,
        "diferenca": difference(a, c),
    }


def by_block(rows: list[dict]) -> list[dict]:
    snaps = {r["id"]: blocks.derive(_snapshot(r)) for r in rows}
    out = []
    for key, title, rule in blocks.BLOCKS:
        out.append({"bloco": key, "titulo": title, "regra": rule, **_concordance(rows, lambda r, k=key: snaps[r["id"]][k])})
    return out


def by_lens(rows: list[dict]) -> dict:
    snaps = {r["id"]: blocks.ai_lenses(_snapshot(r)) for r in rows}
    names = sorted({name for lenses in snaps.values() for name in lenses})
    with_ai = sum(1 for lenses in snaps.values() if lenses)
    versions = Counter()
    for r in rows:
        ai = _snapshot(r).get("ai")
        if isinstance(ai, dict) and ai.get("lenses"):
            versions[(ai.get("prompt_version"), ai.get("model"))] += 1
    return {
        "registros_com_ia": with_ai,
        "versoes": [{"prompt_version": v, "model": m, "registros": n} for (v, m), n in sorted(versions.items(), key=lambda x: -x[1])],
        "lentes": [
            {"lente": name, **_concordance(rows, lambda r, n=name: snaps[r["id"]].get(n))} for name in names
        ],
    }


def by_decision(rows: list[dict]) -> dict:
    lines = []
    for decision in DECISIONS:
        sub = [r for r in rows if r["decision"] == decision]
        c = cell(sub)
        # decisão certa: entrar e a tese bater o alvo; não entrar e a tese ser invalidada
        right = c["alvo"] if decision == "entrei" else c["invalidada"]
        lines.append({"chave": decision, **c, "decisao_certa": rate(right, c["fechadas"])})

    entered = cell([r for r in rows if r["decision"] == "entrei"])
    skipped = cell([r for r in rows if r["decision"] != "entrei"])

    early = [r for r in rows if r["decision"] == "entrei" and r["early_exit_at"]]
    return {
        "linhas": lines,
        "entrei_vs_fora": {"entrei": entered, "fora": skipped, "diferenca": difference(entered, skipped)},
        "saida_antecipada": {"registros": len(early), "depois": cell(early)},
    }


def alerts_review(alerts: list[dict], entries: list[dict]) -> dict:
    by_id = {r["id"]: r for r in entries}
    fired = [a for a in alerts if a["status"] == "disparado"]
    kinds = []
    for kind in ALERT_KINDS:
        sub = [a for a in fired if a["kind"] == kind]
        resp = Counter(a["response"] for a in sub if a["response"])
        kinds.append(
            {
                "tipo": kind,
                "criados": sum(1 for a in alerts if a["kind"] == kind),
                "disparados": len(sub),
                **{r: resp[r] for r in RESPONSES},
                "sem_resposta": sum(1 for a in sub if not a["response"]),
            }
        )

    # Só o alerta de entrada tem um desfecho que ainda não era conhecido na hora da resposta.
    # (Alertas de alvo e invalidação disparam justamente quando a tese termina: medir seria circular.)
    outcome = []
    for response in RESPONSES:
        linked = {
            a["entry_id"]: by_id[a["entry_id"]]
            for a in fired
            if a["kind"] == "entrada" and a["response"] == response and a["entry_id"] in by_id
        }
        outcome.append({"chave": response, **cell(list(linked.values()))})
    return {
        "criados": len(alerts),
        "disparados": len(fired),
        "sem_resposta": sum(1 for a in fired if not a["response"]),
        "cancelados": sum(1 for a in alerts if a["status"] == "cancelado"),
        "por_tipo": kinds,
        "entrada_por_resposta": outcome,
    }


def _warnings(rows: list[dict], overall: dict, lenses: dict) -> list[str]:
    out = []
    if overall["fechadas"] < OK:
        out.append(
            f"Só {overall['fechadas']} tese(s) resolvida(s) (alvo ou invalidada). Abaixo de {OK}, cada número abaixo é anedota: "
            "use para olhar os casos, não para concluir."
        )
    out.append(
        "Há dezenas de comparações aqui (mercados, setups, blocos, lentes). Com intervalo de 95%, uma ou outra vai parecer "
        "distinguível só por acaso: uma diferença só vale se aparecer de novo em registros novos."
    )
    out.append(
        "O desfecho de cada tese é medido a partir do registro, sem exigir que o preço toque a entrada (vale também para "
        "'observando' e 'não entrei'). Registros do mesmo ativo em datas próximas não são independentes."
    )
    if len(lenses["versoes"]) > 1:
        out.append("As lentes de IA misturam versões de prompt ou modelos diferentes: a comparação entre elas fica fraca.")
    return out


def build(entries: list[dict], alerts: list[dict]) -> dict:
    rows = list(entries)
    overall = cell(rows)
    lenses = by_lens(rows)
    dates = sorted(r["created_at"] for r in rows)
    return {
        "regras_versao": blocks.RULES_VERSION,
        "amostra": {
            **overall,
            "ativos_distintos": len({(r["market"], r["symbol"]) for r in rows}),
            "primeiro": dates[0] if dates else None,
            "ultimo": dates[-1] if dates else None,
        },
        "por_decisao": by_decision(rows),
        "por_mercado": _group(rows, lambda r: r["market"]),
        "por_setup": _group(rows, _setup_names),
        "por_bloco": by_block(rows),
        "por_lente": lenses,
        "alertas": alerts_review(alerts, rows),
        "avisos": _warnings(rows, overall, lenses),
    }
