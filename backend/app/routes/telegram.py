"""Telegram: vincular o bot do usuário a uma conversa, testar e ligar/desligar o envio dos alertas de preço.

O token do bot fica só no .env e nunca aparece em nenhuma resposta desta API.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..alerts import telegram
from ..alerts.telegram import TelegramError

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Erro de configuração do usuário = 400; o Telegram fora do ar ou lento = 502.
HTTP_STATUS = {
    "sem_token": 400, "token_recusado": 400, "sem_chat": 400, "chat_nao_encontrado": 400, "bloqueado": 400,
    "conflito": 409, "limite": 429,
}


def _fail(exc: TelegramError) -> HTTPException:
    return HTTPException(HTTP_STATUS.get(exc.kind, 502), exc.message)


class LinkIn(BaseModel):
    chat_id: int | str


class OptionsIn(BaseModel):
    enabled: bool | None = None
    include_note: bool | None = None


def _status() -> dict:
    configured = bool(telegram.token())
    chat_id, label, source = telegram.linked_chat()
    bot, error = None, None
    if configured:
        try:
            bot = telegram.get_me()
        except TelegramError as exc:
            error = exc.message
    return {
        "token_configured": configured,
        "bot": bot,
        "error": error,
        "chat": None if chat_id is None else {"id": chat_id, "label": label, "source": source},
        "enabled": telegram.is_enabled(),
        "include_note": telegram.include_note(),
        "ready": telegram.ready(),
    }


@router.get("/status")
def status():
    return _status()


@router.post("/discover")
def discover():
    """As conversas que escreveram ao bot nas últimas ~24 h. O usuário escolhe qual vincular."""
    try:
        return {"chats": telegram.discover_chats()}
    except TelegramError as exc:
        raise _fail(exc) from exc


@router.post("/link")
def link(body: LinkIn):
    """Vincula uma conversa. Só aceita uma que o próprio bot viu (a lista de `discover`) e confirma com uma mensagem nela."""
    try:
        chats = telegram.discover_chats()
        chosen = next((c for c in chats if str(c["chat_id"]) == str(body.chat_id)), None)
        if chosen is None:
            raise HTTPException(
                404, "Essa conversa não aparece entre as que escreveram ao bot. Mande uma mensagem ao bot e procure de novo."
            )
        telegram.send_text("✅ Trade Journal vinculado a esta conversa. Os alertas de preço chegarão aqui.", str(chosen["chat_id"]))
    except TelegramError as exc:
        raise _fail(exc) from exc
    telegram.link(chosen["chat_id"], chosen["rotulo"])
    return _status()


@router.delete("/link")
def unlink():
    telegram.unlink()
    return _status()


@router.post("/options")
def options(body: OptionsIn):
    telegram.set_options(body.enabled, body.include_note)
    return _status()


@router.post("/test")
def test():
    """Manda uma mensagem de teste ao chat vinculado (mesmo com o envio dos alertas desligado)."""
    try:
        telegram.send_text("🔔 Teste do Trade Journal: se você está vendo isto, os alertas de preço vão chegar assim.")
    except TelegramError as exc:
        raise _fail(exc) from exc
    return {"ok": True}
