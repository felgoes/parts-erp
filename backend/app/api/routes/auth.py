import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import BiometricCredential, User
from app.schemas.common import (
    BiometricCredentialCreate,
    BiometricCredentialLogin,
    BiometricCredentialOut,
    Token,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.lower().strip()))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return Token(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


def _credential_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@router.post("/biometric/credentials", response_model=BiometricCredentialOut)
def create_biometric_credential(
    body: BiometricCredentialCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BiometricCredentialOut:
    raw_credential = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(
        days=get_settings().biometric_credential_days
    )
    db.add(
        BiometricCredential(
            user_id=user.id,
            token_hash=_credential_hash(raw_credential),
            device_name=body.device_name.strip(),
            expires_at=expires_at,
        )
    )
    db.commit()
    return BiometricCredentialOut(credential=raw_credential, expires_at=expires_at)


@router.post("/biometric/login", response_model=Token)
def biometric_login(body: BiometricCredentialLogin, db: Session = Depends(get_db)) -> Token:
    credential = db.scalar(
        select(BiometricCredential).where(
            BiometricCredential.token_hash == _credential_hash(body.credential)
        )
    )
    now = datetime.now(UTC)
    expires_at = credential.expires_at if credential else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        not credential
        or credential.revoked_at is not None
        or expires_at is None
        or expires_at <= now
        or not credential.user.active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso biométrico expirado. Entre com e-mail e senha novamente.",
        )
    credential.last_used_at = now
    db.commit()
    user = credential.user
    return Token(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )
