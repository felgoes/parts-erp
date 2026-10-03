import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx


class ShopeeError(RuntimeError):
    pass

class ShopeeClient:
    base_url = "https://partner.shopeemobile.com"
    def __init__(self, partner_id: str, partner_key: str):
        self.partner_id = partner_id
        self.partner_key = partner_key
    def signature(self, path: str, timestamp: int) -> str:
        raw = f"{self.partner_id}{path}{timestamp}".encode()
        return hmac.new(self.partner_key.encode(), raw, hashlib.sha256).hexdigest()
    def authorization_url(self, redirect_uri: str, state: str | None = None) -> str:
        path = "/api/v2/shop/auth_partner"
        timestamp = int(time.time())
        query = {"partner_id": self.partner_id, "timestamp": timestamp,
                 "sign": self.signature(path, timestamp), "redirect": redirect_uri}
        return f"{self.base_url}{path}?{urlencode(query)}"
    def exchange_code(self, code: str, shop_id: str) -> dict:
        path = "/api/v2/auth/token/get"
        timestamp = int(time.time())
        params = {"partner_id": self.partner_id, "timestamp": timestamp,
                  "sign": self.signature(path, timestamp)}
        response = httpx.post(f"{self.base_url}{path}", params=params, json={
            "code": code, "shop_id": int(shop_id), "partner_id": int(self.partner_id)
        }, timeout=30)
        if response.is_error:
            raise ShopeeError(f"Shopee token exchange failed: {response.status_code}")
        data = response.json()
        if data.get("error"):
            raise ShopeeError(str(data["error"]))
        return data.get("response", data)
