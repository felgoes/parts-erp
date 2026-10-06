from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import MarketplaceAccount, MarketplaceConfig


class MercadoLivreError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MercadoLivreClient:
    def __init__(self, db: Session, account: MarketplaceAccount | None = None) -> None:
        self.db = db
        self.account = account
        self.settings = get_settings()

    def _config(self) -> MarketplaceConfig | None:
        return self.db.scalar(select(MarketplaceConfig).limit(1))

    @property
    def client_id(self) -> str:
        config = self._config()
        return config.client_id if config else self.settings.mercadolivre_client_id

    @property
    def client_secret(self) -> str | None:
        config = self._config()
        if config and config.encrypted_client_secret:
            return decrypt_secret(config.encrypted_client_secret)
        return (
            self.settings.mercadolivre_client_secret.get_secret_value()
            if self.settings.mercadolivre_client_secret
            else None
        )

    @property
    def api_url(self) -> str:
        return self.settings.mercadolivre_api_url

    @property
    def redirect_uri(self) -> str:
        config = self._config()
        return (config.redirect_uri if config else None) or str(
            self.settings.mercadolivre_redirect_uri
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.api_url, timeout=30.0)

    def exchange_code(self, code: str) -> dict[str, Any]:
        secret = self.client_secret
        if not self.client_id or not secret:
            raise MercadoLivreError("Credenciais do Mercado Livre não configuradas")
        response = httpx.post(
            f"{self.api_url}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            timeout=30.0,
        )
        self._raise(response)
        return cast(dict[str, Any], response.json())

    def refresh_access_token(self) -> str:
        if not self.account or not self.account.encrypted_refresh_token:
            raise MercadoLivreError("Conta sem refresh token")
        secret = self.client_secret
        if not secret:
            raise MercadoLivreError("Client secret não configurado")
        response = httpx.post(
            f"{self.api_url}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": secret,
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

    def get(
        self, path: str, extra_headers: dict[str, str] | None = None
    ) -> dict[str, Any] | list[Any]:
        headers = {"Authorization": f"Bearer {self.access_token()}"}
        if extra_headers:
            headers.update(extra_headers)
        with self._client() as client:
            response = client.get(path, headers=headers)
        self._raise(response)
        return cast(dict[str, Any] | list[Any], response.json())

    def get_with_headers(self, path: str) -> tuple[dict[str, Any] | list[Any], dict[str, str]]:
        with self._client() as client:
            response = client.get(path, headers={"Authorization": f"Bearer {self.access_token()}"})
        self._raise(response)
        return cast(dict[str, Any] | list[Any], response.json()), dict(response.headers)

    def put(
        self,
        path: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        headers = {"Authorization": f"Bearer {self.access_token()}"}
        if extra_headers:
            headers.update(extra_headers)
        with self._client() as client:
            response = client.put(path, json=payload, headers=headers)
        self._raise(response)
        if response.status_code == 204 or not response.content:
            return {}
        return cast(dict[str, Any] | list[Any], response.json())

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        with self._client() as client:
            response = client.post(
                path,
                json=payload,
                headers={"Authorization": f"Bearer {self.access_token()}"},
            )
        self._raise(response)
        return cast(dict[str, Any] | list[Any], response.json())

    def upload_picture(self, contents: bytes, filename: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.api_url}/pictures/items/upload",
            headers={"Authorization": f"Bearer {self.access_token()}"},
            files={"file": (filename, contents, "image/jpeg")},
            timeout=60.0,
        )
        self._raise(response)
        return cast(dict[str, Any], response.json())

    def download(self, path: str) -> bytes:
        absolute = path if path.startswith("http") else urljoin(self.api_url, path)
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
        raise MercadoLivreError(
            f"Mercado Livre respondeu {response.status_code}: {detail[:300]}",
            status_code=response.status_code,
        )
