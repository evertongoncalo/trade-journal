"""Alertas de preço: criar, listar, cancelar, responder ao disparo e ver o estado da vigilância."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..alerts import notify, service, store, telegram, watcher
from ..providers.base import ProviderError
from ..providers.symbols import SymbolError, normalize
from ..util import clean_json

router = APIRouter(prefix="/alerts", tags=["alertas"])


class AlertIn(BaseModel):
    market: Literal["acoes", "cripto", "forex"]
    symbol: str
    price: float = Field(gt=0)
    direction: Literal["acima", "abaixo"]
    note: str = Field(default="", max_length=200)


class RespondIn(BaseModel):
    response: Literal["entrei", "ignorei", "observando"]
    note: str = Field(default="", max_length=200)


@router.get("")
def list_alerts():
    return clean_json(store.list_all())


@router.post("", status_code=201)
def create_alert(body: AlertIn):
    try:
        sym = normalize(body.market, body.symbol)
        return clean_json(service.create_manual(body.market, sym, body.price, body.direction, body.note))
    except SymbolError as exc:
        raise HTTPException(422, str(exc)) from exc
    except service.AlertError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(502, f"Não consegui o preço atual para validar o alerta: {exc}") from exc


@router.get("/status")
def status():
    ok, detail = notify.available()
    return clean_json(
        {
            **store.counts(),
            "watcher": watcher.status(),
            "notifications": {"available": ok, "detail": detail},
            "telegram": {"configured": bool(telegram.token()), "ready": telegram.ready()},  # sem rede: só lê a configuração
        }
    )


@router.post("/check")
def check_now():
    """Roda um ciclo de vigilância agora (além do automático)."""
    fired = watcher.check_once()
    return clean_json({"fired": fired, "watcher": watcher.status()})


@router.post("/test-notification")
def test_notification():
    ok, detail = notify.send(
        "Trade Journal: teste de notificação", "Se você está vendo isto, os alertas vão aparecer assim.", config.APP_URL
    )
    return {"ok": ok, "detail": detail}


@router.post("/{alert_id}/cancel")
def cancel_alert(alert_id: int):
    if not store.cancel(alert_id):
        raise HTTPException(404, "Alerta não encontrado ou já não estava ativo")
    return clean_json(store.get(alert_id))


@router.post("/{alert_id}/respond")
def respond(alert_id: int, body: RespondIn):
    if not store.respond(alert_id, body.response, body.note):
        raise HTTPException(404, "Só alertas já disparados podem ser respondidos")
    return clean_json(store.get(alert_id))


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int):
    if not store.delete(alert_id):
        raise HTTPException(404, "Alerta não encontrado")
