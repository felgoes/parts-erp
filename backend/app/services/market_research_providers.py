import ipaddress
import json
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    MarketStudyConnectorConfig,
)


class ResearchProvider(Protocol):
    name: str

    def analyze(self, model: str, api_key: str, prompt: str) -> dict[str, Any]: ...


def _safe_ai_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("A IA não retornou uma análise estruturada") from None
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("A análise da IA veio em um formato inesperado")
    return parsed


class OpenAIResponsesProvider:
    name = "openai_responses"

    def analyze(self, model: str, api_key: str, prompt: str) -> dict[str, Any]:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "store": False,
                "instructions": (
                    "Você é analista de mercado de autopeças no Brasil. "
                    "Use exclusivamente os dados "
                    "fornecidos; diferencie evidência de hipótese; nunca invente giro mensal, "
                    "fornecedor ou compatibilidade. Devolva JSON com summary (string), "
                    "opportunities (array de strings), risks (array de strings), "
                    "next_steps (array de strings) e confidence (low|medium|high)."
                ),
                "input": prompt,
                "max_output_tokens": 900,
            },
            timeout=45.0,
        )
        if not response.is_success:
            raise RuntimeError(f"Provedor de IA respondeu HTTP {response.status_code}")
        body = response.json()
        text = body.get("output_text")
        if not isinstance(text, str):
            text = "\n".join(
                part.get("text", "")
                for output in body.get("output", [])
                if isinstance(output, dict)
                for part in output.get("content", [])
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        return _safe_ai_json(text)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def analyze(self, model: str, api_key: str, prompt: str, base_url: str) -> dict[str, Any]:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Você é analista de mercado de autopeças no Brasil. "
                            "Use apenas evidências recebidas e não invente fornecedores, giro ou "
                            "compatibilidade. Responda "
                            "JSON com summary, opportunities, risks, next_steps e confidence."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=45.0,
        )
        if not response.is_success:
            raise RuntimeError(f"Provedor compatível respondeu HTTP {response.status_code}")
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return _safe_ai_json(content) if isinstance(content, str) else {}


_PROVIDERS: dict[str, Any] = {
    OpenAIResponsesProvider.name: OpenAIResponsesProvider(),
    OpenAICompatibleProvider.name: OpenAICompatibleProvider(),
}


def validate_connector_url(provider: str, value: str | None) -> str | None:
    if provider == "openai_responses":
        return "https://api.openai.com/v1"
    if not value:
        raise ValueError("Informe o endereço HTTPS do provedor compatível")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(
            "O conector personalizado precisa usar HTTPS e não aceitar credenciais na URL"
        )
    hostname = parsed.hostname.lower()
    if (
        hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith((".local", ".internal", ".localhost"))
        or all(character in "0123456789." for character in hostname)
    ):
        raise ValueError("Não é permitido apontar o conector para endereços locais ou internos")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Não é permitido apontar o conector para IP privado ou reservado")
    if parsed.query or parsed.fragment:
        raise ValueError("A URL base não deve conter parâmetros ou fragmentos")
    return value.strip().rstrip("/")


def connector_config(db: Session) -> MarketStudyConnectorConfig | None:
    return db.scalar(
        select(MarketStudyConnectorConfig).order_by(MarketStudyConnectorConfig.created_at).limit(1)
    )


def connector_output(config: MarketStudyConnectorConfig | None) -> dict[str, Any]:
    if not config:
        return {
            "provider": "openai_responses",
            "model": "gpt-6-luna",
            "base_url": None,
            "enabled": False,
            "configured": False,
            "has_api_key": False,
        }
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "enabled": config.enabled,
        "configured": bool(config.encrypted_api_key),
        "has_api_key": bool(config.encrypted_api_key),
    }


def save_connector(
    db: Session,
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    enabled: bool,
) -> MarketStudyConnectorConfig:
    from app.core.security import encrypt_secret

    normalized_url = validate_connector_url(provider, base_url)
    config = connector_config(db)
    if config is None:
        config = MarketStudyConnectorConfig()
        db.add(config)
    config.provider = provider
    config.model = model.strip()
    config.base_url = normalized_url
    config.enabled = enabled
    if api_key and api_key.strip():
        config.encrypted_api_key = encrypt_secret(api_key.strip())
    if enabled and not config.encrypted_api_key:
        raise ValueError("Informe a chave de API antes de ativar a análise com IA")
    db.flush()
    return config
