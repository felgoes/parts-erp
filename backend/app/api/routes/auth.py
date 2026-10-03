from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, client_ip
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.common import Token, UserOut

router = APIRouter(prefix="/auth", tags=["Autenticação"])
_login_limiter = InMemoryRateLimiter()


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    email = form.username.lower().strip()
    remote_ip = client_ip(request.headers, request.client.host if request.client else "unknown")
    limiter_key = sha256(f"{remote_ip}:{email}".encode()).hexdigest()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        settings = get_settings()
        if not _login_limiter.hit(
            limiter_key,
            settings.login_rate_limit_attempts,
            settings.login_rate_limit_window_seconds,
        ):
            raise HTTPException(
                status_code=429, detail="Muitas tentativas; aguarde para tentar novamente"
            )
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    _login_limiter.clear(limiter_key)
    return Token(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
