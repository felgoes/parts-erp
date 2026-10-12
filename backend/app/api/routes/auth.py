import hmac
import math

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, oauth2_scheme, require_permission
from app.core import login_attempts
from app.core.permissions import Permission
from app.core.request_security import client_ip
from app.core.security import (
    biometric_credential_version,
    create_access_token,
    create_biometric_token,
    decode_token,
    verify_password_always,
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
from app.schemas.login_security import LoginAttemptsOut, LoginAttemptsResetIn

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
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    remember_me: bool = Form(False),
) -> Token:
    ip = client_ip(request)
    blocked = login_attempts.block_seconds_left(ip)
    if blocked > 0:
        minutes = max(1, math.ceil(blocked / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Muitas tentativas de login. Aguarde {minutes} minuto(s) ou peça ao "
                "administrador para liberar este acesso."
            ),
        )
    email = form.username.lower().strip()
    # Atraso progressivo por conta: encarece a repetição sem trancar quem sabe a senha.
    login_attempts.pause_for(email)
    user = db.scalar(select(User).where(User.email == email))
    # A verificação roda mesmo sem usuário, para o tempo de resposta não denunciar o e-mail.
    password_ok = verify_password_always(
        form.password, user.password_hash if user is not None else None
    )
    if not user or not user.active or not password_ok:
        login_attempts.register_failure(email, ip)
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    login_attempts.clear_email(email)
    return _issue_token(user, db, remember_me)


@router.get("/attempts", response_model=LoginAttemptsOut)
def list_login_attempts(
    user: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> LoginAttemptsOut:
    """O que está barrado por origem ou atrasado por conta, para liberar na tela."""
    del user
    return LoginAttemptsOut.model_validate(login_attempts.snapshot())


@router.post("/attempts/reset", response_model=LoginAttemptsOut)
def reset_login_attempts(
    body: LoginAttemptsResetIn,
    user: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> LoginAttemptsOut:
    """Libera na hora por e-mail, por origem ou pelas duas, e devolve o estado atualizado."""
    del user
    login_attempts.reset(email=body.normalized_email(), ip=body.ip.strip() if body.ip else None)
    return LoginAttemptsOut.model_validate(login_attempts.snapshot())


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
    return _issue_token(user, db, persistent=True)
