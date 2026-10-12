"""Contrato das tentativas de login (limite por origem e atraso por conta).

Separado de `common.py` para a tela de administração ter um contrato próprio e o arquivo
compartilhado não crescer.
"""

from pydantic import BaseModel, Field, model_validator


class BlockedOriginOut(BaseModel):
    """Origem (IP) barrada temporariamente depois de muitas falhas na janela."""

    ip: str
    failures: int
    seconds_left: int


class DelayedAccountOut(BaseModel):
    """Conta com falhas acumuladas: sofre atraso, mas nunca é bloqueada."""

    email: str
    failures: int
    delay_seconds: float
    seconds_left: int


class LoginAttemptsOut(BaseModel):
    """Estado atual do limitador, para a tela de administração."""

    window_seconds: int
    ip_failure_limit: int
    delay_cap_seconds: float
    blocked_origins: list[BlockedOriginOut] = Field(default_factory=list)
    delayed_accounts: list[DelayedAccountOut] = Field(default_factory=list)


class LoginAttemptsResetIn(BaseModel):
    """Liberação administrativa por e-mail, por origem ou pelas duas."""

    email: str | None = None
    ip: str | None = None

    @model_validator(mode="after")
    def require_a_target(self) -> "LoginAttemptsResetIn":
        if not self.email and not self.ip:
            raise ValueError("Informe o e-mail ou a origem a liberar.")
        return self

    def normalized_email(self) -> str | None:
        return self.email.lower().strip() if self.email else None
