from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import MarketplaceAccount


class MercadoLivreError(RuntimeError):
    pass


class MercadoLivreClient:
    def __init__(self, db: Session, account: MarketplaceAccount | None = None) -> None:
        self.db = db
        self.account = account
        self.settings = get_settings()

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.mercadolivre_api_url, timeout=30.0)

    def exchange_code(self, code: str) -> dict[str, Any]:
        secret = self.settings.mercadolivre_client_secret
        if not self.settings.mercadolivre_client_id or not secret:
            raise MercadoLivreError("Credenciais do Mercado Livre não configuradas")
        response = httpx.post(
            f"{self.settings.mercadolivre_api_url}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.settings.mercadolivre_client_id,
                "client_secret": secret.get_secret_value(),
                "code": code,
                "redirect_uri": str(self.settings.mercadolivre_redirect_uri),
            },
            timeout=30.0,
        )
        self._raise(response)
        return cast(dict[str, Any], response.json())

    def refresh_access_token(self) -> str:
        if not self.account or not self.account.encrypted_refresh_token:
            raise MercadoLivreError("Conta sem refresh token")
        secret = self.settings.mercadolivre_client_secret
        if not secret:
            raise MercadoLivreError("Client secret não configurado")
        response = httpx.post(
            f"{self.settings.mercadolivre_api_url}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.settings.mercadolivre_client_id,
                "client_secret": secret.get_secret_value(),
                "refresh_token": decrypt_secret(self.account.encrypted_refresh_token),
            },
            timeout=30.0,
        )
        self._raise(response)
        tokens = response.json()
        self.account.encrypted_access_token = encrypt_secret(tokens["access_token"])
        if tokens.get("refresh_token"):
            self.account.encrypted_refresh_token = encrypt_secret(tokens["refresh_token"])
        self.account.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens.get("expires_in", 21600)) - 120
        )
        self.db.commit()
        return str(tokens["access_token"])

    def access_token(self) -> str:
        if not self.account:
            raise MercadoLivreError("Conta não conectada")
        expires = self.account.token_expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires and expires <= datetime.now(UTC) + timedelta(minutes=2):
            return self.refresh_access_token()
        return decrypt_secret(self.account.encrypted_access_token)

    def get(self, path: str) -> dict[str, Any] | list[Any]:
        with self._client() as client:
            response = client.get(path, headers={"Authorization": f"Bearer {self.access_token()}"})
        self._raise(response)
        return cast(dict[str, Any] | list[Any], response.json())

    def download(self, path: str) -> bytes:
        absolute = (
            path if path.startswith("http") else urljoin(self.settings.mercadolivre_api_url, path)
        )
        response = httpx.get(
            absolute,
            headers={"Authorization": f"Bearer {self.access_token()}"},
            timeout=60.0,
        )
        self._raise(response)
        return response.content

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            detail = response.json().get("message", response.text)
        except ValueError:
            detail = response.text
        raise MercadoLivreError(f"Mercado Livre respondeu {response.status_code}: {detail[:300]}")
