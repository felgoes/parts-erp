import hmac

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import (
    biometric_credential_version,
    create_access_token,
    create_biometric_token,
    decode_token,
    verify_password,
)
from app.db.session import get_db
from app.models import User
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


@router.post("/biometric/credentials", response_model=BiometricCredentialOut)
def create_biometric_credential(
    body: BiometricCredentialCreate,
    user: User = Depends(get_current_user),
) -> BiometricCredentialOut:
    del body  # Reserved for device audit metadata without exposing it in the token.
    credential, expires_at = create_biometric_token(user.id, user.password_hash)
    return BiometricCredentialOut(credential=credential, expires_at=expires_at)


@router.post("/biometric/login", response_model=Token)
def biometric_login(body: BiometricCredentialLogin, db: Session = Depends(get_db)) -> Token:
    try:
        payload = decode_token(body.credential)
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso biométrico expirado. Entre com e-mail e senha novamente.",
        ) from error
    if payload.get("type") != "biometric" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Credencial biométrica inválida")
    user = db.get(User, str(payload["sub"]))
    expected_version = biometric_credential_version(user.password_hash) if user else ""
    if (
        not user
        or not user.active
        or not hmac.compare_digest(str(payload.get("version", "")), expected_version)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso biométrico revogado. Entre com e-mail e senha novamente.",
        )
    return Token(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )
