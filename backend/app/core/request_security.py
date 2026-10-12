import hmac
import json
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

RATE_LIMIT_WINDOW_SECONDS = 60

# Limitador e deduplicador em memória, válidos porque a API roda em um único processo
# (um uvicorn). Se um dia houver mais de um processo, isto passa a valer por processo e
# deve migrar para o Redis que já existe.
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_seen_once: dict[str, float] = {}
_security_lock = Lock()


def client_ip(request: Request) -> str:
    """IP de quem chamou, atrás do túnel.

    A API só é alcançada pelo Cloudflare Tunnel, então o cabeçalho `cf-connecting-ip` é
    confiável aqui; sem ele, cai para `x-real-ip`, para o primeiro salto de
    `x-forwarded-for` e, por último, para o endereço do peer.
    """
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value and value.strip():
            return value.strip()
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def enforce_rate_limit(
    key: str,
    limit: int,
    *,
    window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    detail: str = "Muitas requisições; tente novamente em instantes",
) -> None:
    """Janela deslizante simples: barra o excesso sem atrapalhar quem usa normalmente."""
    now = monotonic()
    with _security_lock:
        window = _rate_windows[key]
        while window and window[0] <= now - window_seconds:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
        window.append(now)


def remember_once(key: str, ttl_seconds: int) -> bool:
    """Diz se esta chave é nova na janela; repetição dentro do prazo devolve False."""
    now = monotonic()
    with _security_lock:
        if len(_seen_once) > 4096:
            for known, seen_at in list(_seen_once.items()):
                if seen_at <= now - ttl_seconds:
                    _seen_once.pop(known, None)
            if len(_seen_once) > 4096:
                _seen_once.clear()
        seen_at = _seen_once.get(key)
        if seen_at is not None and seen_at > now - ttl_seconds:
            return False
        _seen_once[key] = now
        return True


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
