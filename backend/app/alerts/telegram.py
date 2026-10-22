"""Alertas no Telegram: o disparo de um alerta de preço também vira uma mensagem num bot do próprio usuário.

- O token do bot fica só no .env (`TELEGRAM_BOT_TOKEN`). Ele nunca é logado, nunca vai ao navegador e é apagado de qualquer
  mensagem de erro (a URL da API do Telegram carrega o token).
- O chat de destino é um só e é vinculado pelo usuário na tela: ele manda uma mensagem ao bot, o app lista as conversas que o bot
  viu e o usuário escolhe qual vincular (nunca "a mais recente", para um desconhecido que ache o bot não sequestrar os avisos). Pode
  também vir de `TELEGRAM_CHAT_ID` no .env. O app só ENVIA: não lê comandos nem responde mensagens.
- Falha de envio não atrapalha o alerta (o toast do Windows e o registro no app seguem). Mensagens que falharam são tentadas de novo
  nos ciclos seguintes da vigilância, com espera crescente entre as tentativas (`BACKOFF_SECONDS`), no máximo `MAX_TRIES` tentativas
  no total e só para alertas disparados nas últimas `RETRY_WINDOW_HOURS` horas.
"""
from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from .. import config, settings
from . import store

CHAT_ID = "telegram_chat_id"
CHAT_LABEL = "telegram_chat_label"
ENABLED = "telegram_enabled"
INCLUDE_NOTE = "telegram_include_note"

TIMEOUT = 10  # segundos; a vigilância envia dentro do ciclo, então não pode esperar muito
MAX_TRIES = 6  # a primeira tentativa mais cinco reenvios
BACKOFF_SECONDS = (60, 120, 300, 900, 3600)  # espera depois da 1ª, 2ª, ... tentativa que falhou
RETRY_WINDOW_HOURS = 24
LAG_NOTE_AFTER = timedelta(minutes=15)  # avisa na mensagem quando o app detectou o toque bem depois dele

KIND_TITLE = {
    "avulso": "Alerta de preço",
    "entrada": "Entrada alcançada",
    "invalidacao": "Invalidação tocada",
    "alvo": "Alvo atingido",
}


class TelegramError(Exception):
    """Falha ao falar com o Telegram. `kind` classifica; `message` é para mostrar ao usuário (já sem o token)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def token() -> str:
    return config.TELEGRAM_BOT_TOKEN


def scrub(text: object) -> str:
    """Tira o token de qualquer texto que possa sair do app."""
    out = str(text)
    t = token()
    return out.replace(t, "***") if t else out


def _api_error(code: int, body: dict) -> TelegramError:
    detail = scrub(body.get("description", "")) if isinstance(body, dict) else ""
    low = detail.lower()
    if code in (401, 404):
        return TelegramError("token_recusado", "O Telegram recusou o token. Confira TELEGRAM_BOT_TOKEN no arquivo .env e reinicie o app.")
    if code == 400 and "chat not found" in low:
        return TelegramError("chat_nao_encontrado", "O Telegram não achou esse chat. Mande uma mensagem ao bot e vincule de novo.")
    if code == 403:
        return TelegramError(
            "bloqueado", "O bot não pode escrever nesse chat (foi bloqueado ou removido, ou o chat nunca falou com ele)."
        )
    if code == 409:
        return TelegramError("conflito", "Outro programa está lendo as mensagens deste bot (webhook ou outro app). Pare-o e tente de novo.")
    if code == 429:
        wait = ((body.get("parameters") or {}).get("retry_after")) if isinstance(body, dict) else None
        return TelegramError("limite", f"Limite do Telegram atingido{f'; tente de novo em {wait} s' if wait else ''}.")
    return TelegramError("pedido", f"O Telegram recusou o pedido ({code}): {detail or 'sem detalhe'}")


def call(method: str, params: dict | None = None, timeout: float = TIMEOUT) -> object:
    """Chama um método da API do Bot e devolve `result`. Levanta TelegramError (sem o token na mensagem)."""
    tok = token()
    if not tok:
        raise TelegramError("sem_token", "Defina TELEGRAM_BOT_TOKEN no arquivo .env e reinicie o app.")
    url = f"{config.TELEGRAM_API_URL.rstrip('/')}/bot{tok}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(params or {}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # a API responde com JSON mesmo nos erros
        try:
            err = json.loads(exc.read())
        except (ValueError, OSError):
            err = {}
        raise _api_error(exc.code, err) from None  # `from None`: a causa original carrega a URL com o token
    except TimeoutError:
        raise TelegramError("tempo", "O Telegram não respondeu a tempo.") from None
    except (urllib.error.URLError, OSError) as exc:
        raise TelegramError("rede", f"Sem conexão com o Telegram: {scrub(getattr(exc, 'reason', exc))}") from None
    except ValueError:
        raise TelegramError("resposta_invalida", "O Telegram devolveu uma resposta que não é JSON.") from None
    if not isinstance(body, dict) or not body.get("ok"):
        raise _api_error(int(body.get("error_code", 502)) if isinstance(body, dict) else 502, body if isinstance(body, dict) else {})
    return body.get("result")


# ---------- vínculo ----------


def get_me() -> dict:
    """O bot dono do token: {'username', 'name'}."""
    me = call("getMe")
    return {"username": me.get("username"), "name": me.get("first_name")}  # type: ignore[union-attr]


def _label(chat: dict) -> str:
    if chat.get("type") == "private":
        name = " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p) or "(sem nome)"
        return f"{name} (@{chat['username']})" if chat.get("username") else name
    return chat.get("title") or "(grupo sem título)"


def discover_chats() -> list[dict]:
    """Conversas que escreveram ao bot nas últimas ~24 h (o Telegram só guarda isso), da mais recente para a mais antiga."""
    updates = call("getUpdates", {"limit": 100, "timeout": 0, "allowed_updates": ["message"]})
    seen: dict[int, dict] = {}
    for upd in updates or []:  # type: ignore[union-attr]
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if "id" not in chat or chat.get("type") not in ("private", "group", "supergroup"):
            continue
        seen[chat["id"]] = {  # as mensagens vêm em ordem: a última sobrescreve
            "chat_id": chat["id"],
            "tipo": "privado" if chat["type"] == "private" else "grupo",
            "rotulo": _label(chat),
            "ultima_mensagem": str(msg.get("text") or "")[:80],
            "quando": datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).isoformat(),
        }
    return sorted(seen.values(), key=lambda c: c["quando"], reverse=True)


def env_chat() -> str | None:
    return config.TELEGRAM_CHAT_ID or None


def linked_chat() -> tuple[str | None, str | None, str | None]:
    """(chat_id, rótulo, origem). O .env tem prioridade sobre o vínculo feito na tela."""
    if env_chat():
        return env_chat(), "definido no .env", "env"
    chat = settings.get(CHAT_ID)
    return (chat, settings.get(CHAT_LABEL), "app") if chat else (None, None, None)


def link(chat_id: str | int, label: str) -> None:
    settings.set(CHAT_ID, str(chat_id))
    settings.set(CHAT_LABEL, label)
    settings.set(ENABLED, "1")


def unlink() -> None:
    settings.delete(CHAT_ID, CHAT_LABEL)


def is_enabled() -> bool:
    return settings.get(ENABLED, "1") != "0"


def include_note() -> bool:
    return settings.get(INCLUDE_NOTE, "1") != "0"


def set_options(enabled: bool | None = None, include_note_: bool | None = None) -> None:
    if enabled is not None:
        settings.set(ENABLED, "1" if enabled else "0")
    if include_note_ is not None:
        settings.set(INCLUDE_NOTE, "1" if include_note_ else "0")


def ready() -> bool:
    """Há token, há chat vinculado e o envio não foi desligado."""
    return bool(token()) and linked_chat()[0] is not None and is_enabled()


# ---------- mensagens ----------


def fmt_price(x: float) -> str:
    """Preço sem perder casas (o `:g` do Python corta em 6 algarismos: 81180.23 viraria 81180.2) e sem notação científica."""
    out = f"{x:.8g}"
    return f"{x:.8f}".rstrip("0").rstrip(".") if "e" in out else out


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone().strftime("%d/%m %H:%M")


def format_alert(alert: dict, hit: dict, *, note: bool = True, resent: bool = False) -> str:
    """Texto (HTML do Telegram) de um alerta disparado. Todo texto livre é escapado."""
    up = alert["direction"] == "acima"
    side, verb = ("Máxima", "subiu até") if up else ("Mínima", "caiu até")
    lines = [
        f"🔔 <b>{html.escape(KIND_TITLE.get(alert['kind'], 'Alerta de preço'))}</b>",
        f"<b>{html.escape(alert['symbol'])}</b> {verb} {fmt_price(alert['price'])}",
        f"{side} de {fmt_price(hit['extreme'])} na barra de {_fmt_dt(hit['bar'])}.",
    ]
    detected = alert.get("triggered_at")
    if detected:
        found = datetime.fromisoformat(detected)
        if found.tzinfo is None:
            found = found.replace(tzinfo=timezone.utc)
        if found - hit["bar"] > LAG_NOTE_AFTER:
            lines.append(f"<i>Detectado às {_fmt_dt(found)} (o app estava desligado ou o dado atrasou).</i>")
    if note and alert.get("note"):
        lines.append(html.escape(alert["note"]))
    lines.append("Responda no app (aba Alertas): entrei, ignorei ou observando.")
    if resent:
        lines.append("<i>Reenviada: a primeira tentativa falhou.</i>")
    return "\n".join(lines)


def send_text(text: str, chat_id: str | None = None) -> int:
    """Envia ao chat vinculado (ou ao informado). Devolve o id da mensagem."""
    target = chat_id or linked_chat()[0]
    if not target:
        raise TelegramError("sem_chat", "Nenhum chat vinculado: mande uma mensagem ao bot e vincule a conversa na tela.")
    res = call("sendMessage", {"chat_id": target, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    return int(res["message_id"])  # type: ignore[index]


def notify_alert(alert: dict, hit: dict, *, resent: bool = False) -> tuple[bool, str] | None:
    """Manda o alerta ao Telegram. None = o envio está desligado (nada foi tentado); senão (ok, detalhe). Nunca levanta."""
    if not ready():
        return None
    try:
        send_text(format_alert(alert, hit, note=include_note(), resent=resent))
        return True, "enviada"
    except TelegramError as exc:
        return False, exc.message
    except Exception as exc:  # o ciclo da vigilância não pode cair por causa de um aviso
        return False, scrub(f"falha inesperada: {exc}")


def _aware(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def retry_failed(now: datetime | None = None, exclude: set[int] | frozenset[int] = frozenset()) -> int:
    """Reenvia as mensagens que falharam, respeitando a espera crescente. `exclude`: alertas já tentados neste mesmo ciclo.

    Devolve quantas foram enviadas com sucesso.
    """
    if not ready():
        return 0
    now = now or datetime.now(timezone.utc)
    sent = 0
    for alert in store.telegram_failed(now - timedelta(hours=RETRY_WINDOW_HOURS), MAX_TRIES):
        if alert["id"] in exclude:
            continue
        wait = BACKOFF_SECONDS[min(alert["telegram_tries"], len(BACKOFF_SECONDS)) - 1]
        if alert["telegram_at"] and now - _aware(alert["telegram_at"]) < timedelta(seconds=wait):
            continue
        bar = datetime.fromisoformat(alert["trigger_bar"])
        hit = {"bar": bar if bar.tzinfo else bar.replace(tzinfo=timezone.utc), "extreme": alert["triggered_price"]}
        result = notify_alert(alert, hit, resent=True)
        if result is not None:
            store.set_telegram(alert["id"], *result, at=now)
            sent += bool(result[0])
    return sent
