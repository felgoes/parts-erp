import asyncio

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request

from app.core import request_security
from app.core.request_security import (
    client_ip,
    enforce_rate_limit,
    read_json_object,
    remember_once,
    verify_webhook_secret,
)


def request(body: bytes = b"{}", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": headers or []},
        receive,
    )


def test_webhook_secret_uses_constant_value_from_header():
    valid = request(headers=[(b"x-webhook-token", b"expected")])
    verify_webhook_secret(valid, SecretStr("expected"), production=True)


def test_client_ip_prefers_the_tunnel_header():
    """A API só é alcançada pelo túnel: o cabeçalho do Cloudflare vale mais que o peer."""
    tunnelled = request(headers=[(b"cf-connecting-ip", b"203.0.113.9")])
    assert client_ip(tunnelled) == "203.0.113.9"

    proxied = request(headers=[(b"x-forwarded-for", b"198.51.100.7, 10.0.0.1")])
    assert client_ip(proxied) == "198.51.100.7"


def test_rate_limit_blocks_only_after_the_limit_and_by_key(monkeypatch):
    """Uma janela por chave: o limite barra o excesso sem afetar quem está dentro dele."""
    request_security._rate_windows.clear()
    for _ in range(3):
        enforce_rate_limit("webhook:teste:ip:1", 3)
    with pytest.raises(HTTPException) as error:
        enforce_rate_limit("webhook:teste:ip:1", 3)
    assert error.value.status_code == 429
    # outra chave continua livre
    enforce_rate_limit("webhook:teste:ip:2", 3)


def test_rate_limit_window_expires(monkeypatch):
    request_security._rate_windows.clear()
    clock = {"now": 1000.0}
    monkeypatch.setattr(request_security, "monotonic", lambda: clock["now"])
    enforce_rate_limit("webhook:janela", 1, window_seconds=60)
    with pytest.raises(HTTPException):
        enforce_rate_limit("webhook:janela", 1, window_seconds=60)
    clock["now"] += 61
    enforce_rate_limit("webhook:janela", 1, window_seconds=60)


def test_remember_once_deduplicates_inside_the_window(monkeypatch):
    """Notificação repetida do provedor não entra duas vezes na fila."""
    request_security._seen_once.clear()
    clock = {"now": 500.0}
    monkeypatch.setattr(request_security, "monotonic", lambda: clock["now"])
    assert remember_once("webhook:ml:orders_v2:/orders/1:123", 60) is True
    assert remember_once("webhook:ml:orders_v2:/orders/1:123", 60) is False
    clock["now"] += 61
    assert remember_once("webhook:ml:orders_v2:/orders/1:123", 60) is True


def test_webhook_body_over_the_limit_is_rejected():
    big = request(body=b'{"a": "' + b"x" * (17 * 1024) + b'"}')
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_json_object(big, 16 * 1024))
    assert error.value.status_code == 413

    invalid = request(headers=[(b"x-webhook-token", b"wrong")])
    with pytest.raises(HTTPException) as exc:
        verify_webhook_secret(invalid, SecretStr("expected"), production=True)
    assert exc.value.status_code == 401


def test_production_webhook_requires_configured_secret():
    with pytest.raises(HTTPException) as exc:
        verify_webhook_secret(request(), None, production=True)
    assert exc.value.status_code == 503


def test_webhook_body_size_is_limited():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_json_object(request(b'{"large":"payload"}'), 5))
    assert exc.value.status_code == 413
