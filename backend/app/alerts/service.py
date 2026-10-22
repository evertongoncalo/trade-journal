"""Regras de criação dos alertas: avulsos e os gerados pelos níveis do plano do diário."""
from __future__ import annotations

from ..providers import registry
from . import store

ENTRY_TOLERANCE = 0.001  # entrada a menos de 0,1% do preço atual: não há o que esperar
PLAN_LABEL = {"entrada": "Entrada", "invalidacao": "Invalidação", "alvo": "Alvo"}
PLAN_KINDS = ("entrada", "invalidacao", "alvo")


class AlertError(ValueError):
    """Alerta que não faz sentido (ex.: direção incompatível com o preço atual)."""


def current_price(market: str, symbol: str) -> float:
    return float(registry.fetch(market, symbol, "1h", 5).df["Close"].iloc[-1])


def create_manual(market: str, symbol: str, price: float, direction: str, note: str = "") -> dict:
    """Alerta avulso. A direção precisa combinar com o preço atual: "acima" só faz sentido se o preço está abaixo."""
    current = current_price(market, symbol)
    if direction == "acima" and price <= current:
        raise AlertError(
            f"O preço atual ({current:g}) já está em ou acima de {price:g}. "
            "Para ser avisado quando cair até esse nível, escolha 'abaixo'."
        )
    if direction == "abaixo" and price >= current:
        raise AlertError(
            f"O preço atual ({current:g}) já está em ou abaixo de {price:g}. "
            "Para ser avisado quando subir até esse nível, escolha 'acima'."
        )
    return store.create(market, symbol, price, direction, note, "avulso", None, current)


def plan_specs(entry: dict, current: float | None) -> list[tuple[str, float, str]]:
    """(tipo, nível, direção) dos alertas de um registro do diário.

    - "não entrei": nenhum alerta (o usuário decidiu não agir);
    - "entrei": invalidação e alvo;
    - "observando": também a entrada, se ela estiver longe do preço atual (a ordem de quem espera um recuo).
    """
    if entry["decision"] == "nao_entrei":
        return []
    long = entry["direction"] == "alta"
    specs = [
        ("invalidacao", entry["invalidation"], "abaixo" if long else "acima"),
        ("alvo", entry["target"], "acima" if long else "abaixo"),
    ]
    if entry["decision"] == "observando" and current:
        if abs(entry["entry_price"] - current) / current > ENTRY_TOLERANCE:
            specs.insert(0, ("entrada", entry["entry_price"], "acima" if entry["entry_price"] > current else "abaixo"))
    return specs


def create_plan_alerts(entry: dict) -> list[dict]:
    current = None
    if entry["decision"] == "observando":
        try:
            current = current_price(entry["market"], entry["symbol"])
        except Exception:  # sem preço atual não dá para decidir o alerta de entrada; os outros seguem
            current = None
    created = []
    for kind, price, direction in plan_specs(entry, current):
        note = f"Plano #{entry['id']}: {PLAN_LABEL[kind]}"
        if entry.get("thesis"):
            note += f" — {entry['thesis'][:80]}"
        created.append(store.create(entry["market"], entry["symbol"], price, direction, note, kind, entry["id"], entry["entry_price"]))
    return created


def cancel_for_entry(entry_id: int, reason: str) -> int:
    return store.cancel_for_entry(entry_id, reason, kinds=PLAN_KINDS)
