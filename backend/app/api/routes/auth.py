import hmac

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, oauth2_scheme
from app.core.security import (
    biometric_credential_version,
    create_access_token,
    create_biometric_token,
    decode_token,
    verify_password,
)
from app.db.session import get_db
from app.models import AuthSession, User
from app.schemas.common import (
    BiometricCredentialCreate,
    BiometricCredentialLogin,
    BiometricCredentialOut,
    Token,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _issue_token(user: User, db: Session, persistent: bool = False) -> Token:
    session_id = None
    if persistent:
        auth_session = AuthSession(user_id=user.id)
        db.add(auth_session)
        db.flush()
        session_id = auth_session.id
        db.commit()
    return Token(
        access_token=create_access_token(user.id, user.role.value, session_id),
        persistent=persistent,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    remember_me: bool = Form(False),
) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.lower().strip()))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return _issue_token(user, db, remember_me)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        session_id = decode_token(token).get("sid")
    except jwt.PyJWTError:
        session_id = None
    if session_id:
        db.execute(
            delete(AuthSession).where(
                AuthSession.id == str(session_id),
                AuthSession.user_id == user.id,
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    return _issue_token(user, db)
