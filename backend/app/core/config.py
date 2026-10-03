from functools import lru_cache

from pydantic import AnyHttpUrl, EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: str = "development"
    app_name: str = "Parts ERP"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:4200"
    public_site_url: str = "http://localhost:4300"
    secret_key: SecretStr = Field(min_length=32)
    token_encryption_key: SecretStr
    access_token_minutes: int = 30

    database_url: str = "postgresql+psycopg://parts_erp:parts_erp@localhost:5432/parts_erp"
    redis_url: str = "redis://localhost:6379/0"
    documents_dir: str = "data/documents"

    bootstrap_admin_email: EmailStr = Field(default="admin@example.com")
    bootstrap_admin_password: SecretStr | None = None

    mercadolivre_client_id: str = ""
    mercadolivre_client_secret: SecretStr | None = None
    mercadolivre_redirect_uri: AnyHttpUrl = AnyHttpUrl(
        "http://localhost:8000/api/v1/integrations/mercadolivre/callback"
    )
    mercadolivre_site_id: str = "MLB"
    mercadolivre_api_url: str = "https://api.mercadolibre.com"
    mercadolivre_auth_url: str = "https://auth.mercadolivre.com.br/authorization"
    mercadolivre_auto_issue_invoice: bool = True
    mercadolivre_auto_download_label: bool = True
    mercadolivre_label_format: str = "pdf"
    shopee_partner_id: str = ""
    shopee_partner_key: SecretStr | None = None
    shopee_redirect_uri: AnyHttpUrl = AnyHttpUrl(
        "http://localhost:8000/api/v1/integrations/shopee/callback"
    )
    webhook_shared_secret: SecretStr | None = None
    webhook_max_body_bytes: int = 131_072
    telemetry_rate_limit_per_minute: int = 60
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    @field_validator("token_encryption_key")
    @classmethod
    def validate_encryption_key(cls, value: SecretStr) -> SecretStr:
        from cryptography.fernet import Fernet

        Fernet(value.get_secret_value().encode())
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
