import hmac
import json
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import SecretStr


def verify_webhook_secret(
    request: Request,
    secret: SecretStr | None,
    *,
    production: bool,
) -> None:
    """Validate a webhook token without leaking timing information."""
    if secret is None:
        if production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Segredo do webhook não configurado",
            )
        return
    supplied = request.headers.get("x-webhook-token", "")
    if not hmac.compare_digest(supplied, secret.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token do webhook inválido",
        )


async def read_json_object(request: Request, max_bytes: int) -> dict[str, Any]:
    """Read a bounded JSON request body and require an object payload."""
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload do webhook excede o limite permitido",
        )
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload JSON inválido",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O payload deve ser um objeto JSON",
        )
    return payload
