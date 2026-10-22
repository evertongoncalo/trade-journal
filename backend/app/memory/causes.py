"""Causas de falha em lista fixa (`causas-v1`) e a visibilidade da informação na época.

A lista é fixa de propósito: a IA escolhe UMA causa principal entre estas, nunca inventa outra. "sem_causa_identificavel"
é uma resposta normal e frequente, e o texto do prompt manda preferi-la a uma história plausível. Mudar a lista exige
`causas-v2` (a versão fica gravada em cada pós-mortem e entra na impressão digital do prompt).
"""
from __future__ import annotations

from dataclasses import dataclass

CAUSES_VERSION = "causas-v1"


@dataclass(frozen=True)
class Cause:
    id: str
    title: str
    definition: str  # lido pela IA no prompt e mostrado na tela
    only_if_entered: bool = False  # só faz sentido para quem entrou na operação


CAUSES: tuple[Cause, ...] = (
    Cause(
        "evento_macro",
        "Evento macro",
        "Um movimento brusco em dólar, juros, VIX ou índices durante o caso (veja `depois.referencias` e "
        "`depois.referencias_notaveis`) coincide com o desfecho. O calendário econômico NÃO está nos dados: sem movimento "
        "medido nas referências, não use esta causa.",
    ),
    Cause(
        "referencia_divergiu",
        "Referência divergiu",
        "Uma referência com relação estável com o ativo (`visivel_na_epoca.correlacao`, só com status \"estável\") se moveu "
        "contra a tese durante o caso (`depois.referencias`), ou já divergia do ativo no registro.",
    ),
    Cause(
        "indicador_deu_ruido",
        "Indicador deu ruído",
        "O sinal que sustentava a tese no registro era fraco ou conflitante (blocos de código divididos, probabilidade "
        "histórica indistinta ou sem dados, lentes de IA em desacordo) e o preço não o confirmou.",
    ),
    Cause(
        "invalidacao_ignorada",
        "Invalidação ignorada",
        "Só para quem entrou. O preço tocou a invalidação (`depois.caminho_do_preco.invalidacao_tocada_em`) antes da saída "
        "registrada pelo operador (`depois.caminho_do_preco.saida_antecipada.invalidacao_tocada_antes`). Sem saída "
        "registrada, o app não sabe se a invalidação foi respeitada: não use esta causa.",
        only_if_entered=True,
    ),
    Cause(
        "entrada_tardia",
        "Entrada tardia",
        "Só para quem entrou. No registro, o movimento a favor da tese já estava esticado (`visivel_na_epoca.esticado`: "
        "variação recente a favor, distância da MM20 em ATR, RSI) e o preço devolveu.",
        only_if_entered=True,
    ),
    Cause(
        "sem_causa_identificavel",
        "Sem causa identificável",
        "Os dados do pacote não sustentam nenhuma das causas acima. É uma resposta normal e frequente: prefira-a a uma "
        "história plausível que os dados não provam.",
    ),
)

CAUSE_IDS = tuple(c.id for c in CAUSES)
CAUSE_BY_ID = {c.id: c for c in CAUSES}
NO_CAUSE = "sem_causa_identificavel"

# O que já dava para ver na época do registro × o que só ficou claro depois (viés retrospectivo).
VISIBILITY = ("visivel_na_epoca", "so_ficou_claro_depois", "misto", "nao_se_aplica")


def catalog() -> list[dict]:
    return [{"id": c.id, "title": c.title, "definition": c.definition, "only_if_entered": c.only_if_entered} for c in CAUSES]
