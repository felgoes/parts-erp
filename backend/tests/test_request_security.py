import asyncio

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request

from app.core.request_security import read_json_object, verify_webhook_secret


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
