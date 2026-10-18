"""Adaptadores HTTP dos quatro provedores aprovados.

O restante do assistente fala apenas o formato genérico de mensagens abaixo, então trocar
de provedor não duplica regras de negócio, confirmação ou orçamento.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.assistant.catalog import PROVIDERS
from app.core.config import get_settings


class AssistantProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


def _request(url: str, *, headers: dict[str, str], payload: dict) -> dict:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=60)
    except httpx.TimeoutException:
        raise AssistantProviderError("O provedor demorou demais para responder", 504) from None
    except httpx.HTTPError:
        raise AssistantProviderError("Não foi possível falar com o provedor") from None
    if response.status_code >= 400:
        messages = {
            400: "O provedor recusou a solicitação (modelo ou parâmetros incompatíveis)",
            401: "Chave de API recusada pelo provedor",
            402: "Saldo ou acesso indisponível no provedor",
            403: "Chave de API sem acesso ao modelo escolhido",
            404: "Modelo não encontrado no provedor",
            429: "Limite de uso do provedor atingido",
        }
        raise AssistantProviderError(
            messages.get(response.status_code, "Provedor de IA indisponível"),
            502 if response.status_code >= 500 else 424,
        )
    try:
        data = response.json()
    except ValueError:
        raise AssistantProviderError("O provedor devolveu uma resposta inválida") from None
    if not isinstance(data, dict):
        raise AssistantProviderError("O provedor devolveu uma resposta inválida")
    return data


def _base_url(provider: str) -> str:
    settings = get_settings()
    if settings.app_env != "production" and settings.assistant_base_url_override:
        return settings.assistant_base_url_override.rstrip("/")
    return PROVIDERS[provider].base_url


def _openai_messages(messages: list[dict]) -> list[dict]:
    converted = []
    for message in messages:
        if message["role"] == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id", ""),
                    "content": message.get("content", ""),
                }
            )
        elif message["role"] == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": _json(call.arguments),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        else:
            converted.append({"role": message["role"], "content": message.get("content", "")})
    return converted


def _json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _openai(
    provider: str, model: str, api_key: str, messages: list[dict], tools: list[dict]
) -> ModelReply:
    payload = {
        "model": model,
        "messages": _openai_messages(messages),
        "max_tokens": 1200,
    }
    if tools:
        payload["tools"] = [
            {"type": "function", "function": tool} for tool in tools
        ]
        payload["tool_choice"] = "auto"
    data = _request(
        f"{_base_url(provider)}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
    )
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise AssistantProviderError("O provedor devolveu uma resposta vazia")
    message = choices[0].get("message") or {}
    calls = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") or {}
        calls.append(
            ToolCall(
                id=str(raw.get("id") or ""),
                name=str(function.get("name") or ""),
                arguments=_loads(function.get("arguments")),
            )
        )
    usage = data.get("usage") or {}
    return ModelReply(
        content=str(message.get("content") or ""),
        tool_calls=calls,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )


def _loads(value: object) -> dict[str, Any]:
    import json

    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n\n".join(
        str(message.get("content") or "") for message in messages if message["role"] == "system"
    )
    converted: list[dict] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id", ""),
                            "content": message.get("content", ""),
                        }
                    ],
                }
            )
        elif role == "assistant" and message.get("tool_calls"):
            blocks: list[dict] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            blocks.extend(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
                for call in message["tool_calls"]
            )
            converted.append({"role": "assistant", "content": blocks})
        else:
            converted.append({"role": role, "content": message.get("content", "")})
    return system, converted


def _anthropic(
    provider: str, model: str, api_key: str, messages: list[dict], tools: list[dict]
) -> ModelReply:
    system, converted = _anthropic_messages(messages)
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 1200,
        "messages": converted,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]
    data = _request(
        f"{_base_url(provider)}/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    text: list[str] = []
    calls: list[ToolCall] = []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            calls.append(
                ToolCall(
                    id=str(block.get("id") or ""),
                    name=str(block.get("name") or ""),
                    arguments=block.get("input") if isinstance(block.get("input"), dict) else {},
                )
            )
    usage = data.get("usage") or {}
    return ModelReply(
        content="\n".join(part for part in text if part).strip(),
        tool_calls=calls,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )


def _gemini_contents(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n\n".join(
        str(message.get("content") or "") for message in messages if message["role"] == "system"
    )
    contents: list[dict] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message.get("tool_name", "tool"),
                                "response": {"result": message.get("content", "")},
                            }
                        }
                    ],
                }
            )
        elif role == "assistant" and message.get("tool_calls"):
            parts: list[dict] = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            parts.extend(
                {
                    "functionCall": {
                        "name": call.name,
                        "args": call.arguments,
                    }
                }
                for call in message["tool_calls"]
            )
            contents.append({"role": "model", "parts": parts})
        else:
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": message.get("content", "")}],
                }
            )
    return system, contents


def _gemini(
    provider: str, model: str, api_key: str, messages: list[dict], tools: list[dict]
) -> ModelReply:
    system, contents = _gemini_contents(messages)
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 1200},
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}
    if tools:
        payload["tools"] = [
            {
                "function_declarations": [
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                    }
                    for tool in tools
                ]
            }
        ]
    data = _request(
        f"{_base_url(provider)}/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        payload=payload,
    )
    candidates = data.get("candidates") or []
    if not candidates:
        raise AssistantProviderError("O provedor devolveu uma resposta vazia")
    text: list[str] = []
    calls: list[ToolCall] = []
    for index, part in enumerate((candidates[0].get("content") or {}).get("parts") or []):
        if "text" in part:
            text.append(str(part.get("text") or ""))
        if "functionCall" in part:
            function = part["functionCall"] or {}
            calls.append(
                ToolCall(
                    id=f"gemini-{index}",
                    name=str(function.get("name") or ""),
                    arguments=function.get("args")
                    if isinstance(function.get("args"), dict)
                    else {},
                )
            )
    usage = data.get("usageMetadata") or {}
    return ModelReply(
        content="\n".join(part for part in text if part).strip(),
        tool_calls=calls,
        input_tokens=int(usage.get("promptTokenCount") or 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
    )


def complete(
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> ModelReply:
    if provider not in PROVIDERS:
        raise AssistantProviderError("Provedor não suportado", 400)
    handlers = {
        "openai": _openai,
        "deepseek": _openai,
        "anthropic": _anthropic,
        "gemini": _gemini,
    }
    return handlers[provider](provider, model, api_key, messages, tools or [])
