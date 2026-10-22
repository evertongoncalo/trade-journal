import io
import json
import urllib.error

import pytest

from app import config
from app.ai import client
from app.ai.client import AIError

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"], "additionalProperties": False}
GOOD = {"inclinacao": "indistinta"}


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok_payload(content=None, finish="stop", **extra):
    return {
        "id": "gen-1",
        "model": "anthropic/claude-sonnet-5.5",
        "choices": [{"message": {"content": json.dumps(GOOD) if content is None else content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "cost": 0.0055},
        **extra,
    }


def http_error(code, message="x"):
    body = json.dumps({"error": {"message": message, "code": code}}).encode()
    return urllib.error.HTTPError(client.API_URL, code, "err", {}, io.BytesIO(body))


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-teste")
    monkeypatch.setattr(config, "AI_MODEL", "anthropic/claude-sonnet-5.5")
    monkeypatch.setattr(config, "AI_REASONING_EFFORT", "low")


def script(monkeypatch, *steps):
    """Cada passo é um payload (resposta 200) ou uma exceção a levantar; devolve a lista de requisições feitas."""
    calls, queue = [], list(steps)

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data), "timeout": timeout})
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, BaseException):
            raise step
        return FakeResponse(step)

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    return calls


def chat(**kw):
    return client.chat_json("sistema", "usuario", SCHEMA, sleep=lambda s: None, **kw)


def test_request_shape_and_parsed_result(key, monkeypatch):
    calls = script(monkeypatch, ok_payload())
    res = chat()
    body, headers = calls[0]["body"], calls[0]["headers"]
    assert calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-or-teste" and headers["X-title"] == "Trade Journal"
    assert body["model"] == "anthropic/claude-sonnet-5.5" and body["stream"] is False
    assert body["messages"] == [{"role": "system", "content": "sistema"}, {"role": "user", "content": "usuario"}]
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "lente", "strict": True, "schema": SCHEMA}}
    assert body["provider"] == {"require_parameters": True}
    assert body["reasoning"] == {"effort": "low"} and body["max_tokens"] == config.AI_MAX_TOKENS
    assert "temperature" not in body
    assert res.data == GOOD and res.usage == {"prompt_tokens": 1200, "completion_tokens": 300, "cost": 0.0055}
    assert res.model == "anthropic/claude-sonnet-5.5" and res.generation_id == "gen-1"


def test_empty_effort_sends_no_reasoning_and_overrides_work(key, monkeypatch):
    monkeypatch.setattr(config, "AI_REASONING_EFFORT", "")
    calls = script(monkeypatch, ok_payload())
    chat(model="anthropic/claude-haiku-5.5", max_tokens=1000)
    assert "reasoning" not in calls[0]["body"]
    assert calls[0]["body"]["model"] == "anthropic/claude-haiku-5.5" and calls[0]["body"]["max_tokens"] == 1000


def test_missing_key_fails_before_any_network_call(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    calls = script(monkeypatch, ok_payload())
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "sem_chave" and ".env" in exc.value.message and calls == []
    assert client.configured() is False


@pytest.mark.parametrize("code,kind", [(401, "auth"), (402, "creditos"), (400, "pedido"), (404, "pedido")])
def test_errors_that_do_not_deserve_a_retry(key, monkeypatch, code, kind):
    calls = script(monkeypatch, http_error(code, "model not found"))
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == kind and len(calls) == 1
    if kind == "pedido":
        assert "model not found" in exc.value.message


def test_rate_limit_retries_with_backoff_then_gives_up(key, monkeypatch):
    calls = script(monkeypatch, http_error(429))
    sleeps = []
    with pytest.raises(AIError) as exc:
        client.chat_json("s", "u", SCHEMA, sleep=sleeps.append)
    assert exc.value.kind == "limite" and len(calls) == client.MAX_ATTEMPTS and sleeps == [1.5, 3.0]


def test_server_error_then_success(key, monkeypatch):
    calls = script(monkeypatch, http_error(503, "provider down"), ok_payload())
    assert chat().data == GOOD and len(calls) == 2


def test_network_failure_and_timeout(key, monkeypatch):
    calls = script(monkeypatch, urllib.error.URLError("sem rota"))
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "rede" and "sem rota" in exc.value.message and len(calls) == client.MAX_ATTEMPTS
    script(monkeypatch, TimeoutError())
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "tempo"


def test_provider_error_inside_a_200_response(key, monkeypatch):
    script(monkeypatch, {"error": {"message": "credits exhausted", "code": 402}})
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "creditos"


def test_truncated_response_gives_actionable_message(key, monkeypatch):
    script(monkeypatch, ok_payload(content="", finish="length"))
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "truncado" and "AI_REASONING_EFFORT" in exc.value.message


def test_refusal_empty_and_no_choices(key, monkeypatch):
    script(monkeypatch, {"choices": [{"message": {"content": None, "refusal": "não posso"}, "finish_reason": "stop"}]})
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "recusa"
    script(monkeypatch, {"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]})
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "resposta_invalida"
    script(monkeypatch, {"choices": []})
    with pytest.raises(AIError):
        chat()


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"inclinacao": "indistinta"}\n```',
        'Aqui está: {"inclinacao": "indistinta"} fim',
        [{"type": "text", "text": '{"inclinacao": '}, {"type": "text", "text": '"indistinta"}'}],
    ],
)
def test_tolerates_fenced_wrapped_and_multipart_json(key, monkeypatch, content):
    script(monkeypatch, ok_payload(content=content))
    assert chat().data == GOOD


@pytest.mark.parametrize("content", ["sem json aqui", '{"quebrado": ', "[1, 2, 3]"])
def test_invalid_json_is_reported(key, monkeypatch, content):
    script(monkeypatch, ok_payload(content=content))
    with pytest.raises(AIError) as exc:
        chat()
    assert exc.value.kind == "resposta_invalida"


def test_usage_without_cost_is_kept_as_none(key, monkeypatch):
    payload = ok_payload()
    payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5}
    script(monkeypatch, payload)
    assert chat().usage == {"prompt_tokens": 10, "completion_tokens": 5, "cost": None}
