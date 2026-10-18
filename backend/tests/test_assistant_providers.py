import json

import pytest

from app.assistant import providers
from app.assistant.providers import AssistantProviderError, ToolCall


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def payload_for(provider: str) -> dict:
    if provider in {"openai", "deepseek"}:
        return {
            "choices": [
                {
                    "message": {
                        "content": "Vou consultar.",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "buscar_produtos",
                                    "arguments": json.dumps({"termo": "filtro"}),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30},
        }
    if provider == "anthropic":
        return {
            "content": [
                {"type": "text", "text": "Vou consultar."},
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "buscar_produtos",
                    "input": {"termo": "filtro"},
                },
            ],
            "usage": {"input_tokens": 120, "output_tokens": 30},
        }
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Vou consultar."},
                        {
                            "functionCall": {
                                "name": "buscar_produtos",
                                "args": {"termo": "filtro"},
                            }
                        },
                    ]
                }
            }
        ],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
    }


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-4.1-mini"),
        ("deepseek", "deepseek-chat"),
        ("gemini", "gemini-2.5-flash"),
        ("anthropic", "claude-sonnet-4-5"),
    ],
)
def test_each_provider_returns_text_tool_call_and_usage(monkeypatch, provider, model):
    seen: dict = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, payload=json)
        return FakeResponse(200, payload_for(provider))

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = providers.complete(
        provider,
        model,
        "example-key",
        [
            {"role": "system", "content": "regras"},
            {"role": "user", "content": "consulte o filtro"},
        ],
        [
            {
                "name": "buscar_produtos",
                "description": "consulta",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )
    assert reply.content == "Vou consultar."
    call_id = {"anthropic": "tool-1", "gemini": "gemini-1"}.get(provider, "call-1")
    assert reply.tool_calls == [
        ToolCall(call_id, "buscar_produtos", {"termo": "filtro"})
    ]
    assert (reply.input_tokens, reply.output_tokens) == (120, 30)
    assert "example-key" not in seen["url"]


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (401, "recusada"),
        (402, "Saldo"),
        (429, "Limite"),
        (500, "indisponível"),
    ],
)
def test_provider_errors_are_friendly_and_do_not_echo_body(monkeypatch, status, fragment):
    marker = "sensitive-response-marker"

    def fake_post(*args, **kwargs):
        return FakeResponse(status, {"error": marker})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(AssistantProviderError) as captured:
        providers.complete(
            "openai", "gpt-4.1-mini", "key", [{"role": "user", "content": "oi"}]
        )
    assert fragment.lower() in captured.value.message.lower()
    assert marker not in captured.value.message


def test_timeout_is_reported_without_secret(monkeypatch):
    import httpx

    def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(AssistantProviderError) as captured:
        providers.complete(
            "gemini", "gemini-2.5-flash", "secret-key", [{"role": "user", "content": "oi"}]
        )
    assert "demorou" in captured.value.message
    assert "secret-key" not in captured.value.message
