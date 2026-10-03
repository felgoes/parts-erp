import json
import secrets

from fastapi import HTTPException, Request
from pydantic import SecretStr


async def read_json_object(request: Request, max_bytes: int) -> dict[str, object]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail="Corpo da requisição muito grande")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length inválido") from exc

    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Corpo da requisição muito grande")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="JSON inválido") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="O corpo deve ser um objeto JSON")
    return payload


def verify_webhook_secret(
    request: Request, configured_secret: SecretStr | None, production: bool
) -> None:
    if configured_secret is None:
        if production:
            raise HTTPException(status_code=503, detail="Segredo de webhook não configurado")
        return

    received = request.headers.get("x-webhook-token") or request.query_params.get("token") or ""
    if not secrets.compare_digest(received, configured_secret.get_secret_value()):
        raise HTTPException(status_code=401, detail="Token de webhook inválido")
