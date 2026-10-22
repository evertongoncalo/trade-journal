"""Cliente da OpenRouter (API de chat compatível com o formato da OpenAI), só com a biblioteca padrão.

A chave vem de OPENROUTER_API_KEY no .env e nunca é logada nem enviada ao navegador. A saída é pedida em JSON com
esquema (`response_format: json_schema`) e o pedido só roda em provedores que aceitam todos os parâmetros enviados
(`provider.require_parameters`); mesmo assim o texto é validado de novo por quem chama, porque nem todo provedor
garante o esquema.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .. import config

API_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRY_KINDS = {"limite", "servidor", "rede", "tempo"}
MAX_ATTEMPTS = 3


class AIError(Exception):
    """Falha ao falar com o modelo. `kind` classifica; `message` é para mostrar ao usuário."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class ChatResult:
    data: dict
    text: str
    usage: dict = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""
    generation_id: str | None = None


def configured() -> bool:
    return bool(config.OPENROUTER_API_KEY)


def parse_json_text(text: str) -> dict:
    """Aceita JSON puro ou embrulhado em ```json ... ``` ou com texto em volta."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise AIError("resposta_invalida", "A resposta do modelo não contém JSON.")
    try:
        obj = json.loads(t[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIError("resposta_invalida", f"JSON inválido na resposta do modelo: {exc.msg}.") from exc
    if not isinstance(obj, dict):
        raise AIError("resposta_invalida", "A resposta do modelo não é um objeto JSON.")
    return obj


def _http_error(status: int, body: str) -> AIError:
    detail = ""
    try:
        err = json.loads(body).get("error", {})
        detail = err.get("message", "") if isinstance(err, dict) else str(err)
    except (json.JSONDecodeError, AttributeError):
        detail = body[:200]
    if status == 401:
        return AIError("auth", "A OpenRouter recusou a chave. Confira OPENROUTER_API_KEY no arquivo .env.")
    if status == 402:
        return AIError("creditos", "Sem saldo na OpenRouter. Adicione créditos em openrouter.ai/credits.")
    if status == 429:
        return AIError("limite", "Limite de requisições da OpenRouter. Tente de novo em instantes.")
    if status == 408:
        return AIError("tempo", "A OpenRouter não respondeu a tempo.")
    if status >= 500:
        return AIError("servidor", f"OpenRouter ou o provedor do modelo indisponível ({status}). {detail}".strip())
    return AIError("pedido", f"A OpenRouter recusou o pedido ({status}): {detail or 'sem detalhe'}")


def _extract_text(raw: dict) -> tuple[str, str]:
    """(texto, finish_reason) da primeira escolha; levanta AIError se não houver conteúdo."""
    if isinstance(raw.get("error"), dict):  # erro de provedor dentro de uma resposta 200
        code = raw["error"].get("code")
        raise _http_error(int(code) if isinstance(code, int) else 502, json.dumps({"error": raw["error"]}))
    choices = raw.get("choices") or []
    if not choices:
        raise AIError("resposta_invalida", "A OpenRouter respondeu sem nenhuma escolha.")
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # alguns provedores devolvem partes
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    finish = choice.get("finish_reason") or ""
    if not content or not str(content).strip():
        if finish == "length":
            raise AIError(
                "truncado",
                "O modelo gastou todo o limite de tokens antes de responder. Reduza AI_REASONING_EFFORT ou aumente AI_MAX_TOKENS.",
            )
        if message.get("refusal") or finish == "content_filter":
            raise AIError("recusa", "O modelo recusou responder.")
        raise AIError("resposta_invalida", "O modelo devolveu uma resposta vazia.")
    return str(content), finish


def chat_json(
    system: str,
    user: str,
    schema: dict,
    *,
    model: str | None = None,
    effort: str | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    sleep=time.sleep,
) -> ChatResult:
    key = config.OPENROUTER_API_KEY
    if not key:
        raise AIError("sem_chave", "Defina OPENROUTER_API_KEY no arquivo .env e reinicie o app.")
    model = model or config.AI_MODEL
    effort = config.AI_REASONING_EFFORT if effort is None else effort
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens or config.AI_MAX_TOKENS,
        "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {"name": "lente", "strict": True, "schema": schema}},
        "provider": {"require_parameters": True},
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.APP_URL,
        "X-Title": "Trade Journal",
    }

    last: AIError | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            sleep(1.5 * attempt)
        try:
            req = urllib.request.Request(config.OPENROUTER_API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout or config.AI_TIMEOUT_SECONDS) as resp:
                raw = json.loads(resp.read())
            text, finish = _extract_text(raw)
            break
        except urllib.error.HTTPError as exc:
            last = _http_error(exc.code, exc.read().decode("utf-8", "replace"))
        except AIError as exc:
            last = exc
        except TimeoutError:
            last = AIError("tempo", "A OpenRouter não respondeu a tempo.")
        except (urllib.error.URLError, OSError) as exc:
            last = AIError("rede", f"Sem conexão com a OpenRouter: {getattr(exc, 'reason', exc)}")
        except json.JSONDecodeError:
            last = AIError("resposta_invalida", "A OpenRouter devolveu uma resposta que não é JSON.")
        if last.kind not in RETRY_KINDS:
            raise last
    else:
        raise last  # type: ignore[misc]

    usage = raw.get("usage") or {}
    return ChatResult(
        data=parse_json_text(text),
        text=text,
        usage={
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cost": usage.get("cost"),
        },
        model=raw.get("model") or model,
        finish_reason=finish,
        generation_id=raw.get("id"),
    )
