from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import MarketplaceAccount, ShopeeConfig


class ShopeeError(RuntimeError):
    pass


class ShopeeClient:
    base_url = "https://partner.shopeemobile.com"

    def __init__(
        self, partner_id: str, partner_key: str, account: MarketplaceAccount | None = None
    ):
        self.partner_id = str(partner_id)
        self.partner_key = partner_key
        self.account = account

    @classmethod
    def from_account(cls, account: MarketplaceAccount) -> ShopeeClient:
        settings = get_settings()
        session = object_session(account)
        config = session.scalar(select(ShopeeConfig).limit(1)) if session else None
        partner_id = config.partner_id if config else settings.shopee_partner_id
        if config and config.encrypted_partner_key:
            key = decrypt_secret(config.encrypted_partner_key)
        else:
            key = (
                settings.shopee_partner_key.get_secret_value()
                if settings.shopee_partner_key
                else ""
            )
        return cls(partner_id, key, account)

    def signature(
        self, path: str, timestamp: int, access_token: str = "", shop_id: str = ""
    ) -> str:
        raw = f"{self.partner_id}{path}{timestamp}{access_token}{shop_id}".encode()
        return hmac.new(self.partner_key.encode(), raw, hashlib.sha256).hexdigest()

    def authorization_url(self, redirect_uri: str, state: str | None = None) -> str:
        path = "/api/v2/shop/auth_partner"
        timestamp = int(time.time())
        query = {
            "partner_id": self.partner_id,
            "timestamp": timestamp,
            "sign": self.signature(path, timestamp),
            "redirect": redirect_uri,
        }
        return f"{self.base_url}{path}?{urlencode(query)}"

    def exchange_code(self, code: str, shop_id: str) -> dict[str, Any]:
        path = "/api/v2/auth/token/get"
        timestamp = int(time.time())
        params: dict[str, str | int] = {
            "partner_id": self.partner_id,
            "timestamp": timestamp,
            "sign": self.signature(path, timestamp),
        }
        response = httpx.post(
            f"{self.base_url}{path}",
            params=params,
            json={"code": code, "shop_id": int(shop_id), "partner_id": int(self.partner_id)},
            timeout=30,
        )
        self._raise(response)
        data = cast(dict[str, Any], response.json())
        return cast(dict[str, Any], data.get("response", data))

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.account:
            raise ShopeeError("Shop account not connected")
        access_token = decrypt_secret(self.account.encrypted_access_token)
        shop_id = str(self.account.seller_id)
        timestamp = int(time.time())
        query = dict(params)
        query.update(
            {
                "partner_id": int(self.partner_id),
                "timestamp": timestamp,
                "access_token": access_token,
                "shop_id": int(shop_id),
                "sign": self.signature(path, timestamp, access_token, shop_id),
            }
        )
        response = httpx.get(f"{self.base_url}{path}", params=query, timeout=30)
        self._raise(response)
        data = cast(dict[str, Any], response.json())
        if data.get("error"):
            raise ShopeeError(str(data.get("message") or data["error"]))
        return cast(dict[str, Any], data.get("response", data))

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_success:
            return
        raise ShopeeError(f"Shopee responded {response.status_code}: {response.text[:300]}")
