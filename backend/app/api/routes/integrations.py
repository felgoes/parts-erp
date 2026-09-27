import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import jwt
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.security import decode_token, encrypt_secret
from app.db.session import get_db
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import MarketplaceAccount, MarketplaceOrder, User, UserRole
from app.schemas.common import MarketplaceOrderOut, MarketplaceStatus

router = APIRouter(prefix="/integrations/mercadolivre", tags=["Mercado Livre"])


@router.get("/status", response_model=MarketplaceStatus)
def status(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> MarketplaceStatus:
    settings = get_settings()
    account = db.scalar(
        select(MarketplaceAccount).where(MarketplaceAccount.active.is_(True)).limit(1)
    )
    return MarketplaceStatus(
        configured=bool(settings.mercadolivre_client_id and settings.mercadolivre_client_secret),
        connected=account is not None,
        seller_id=account.seller_id if account else None,
        nickname=account.nickname if account else None,
        token_expires_at=account.token_expires_at if account else None,
    )


@router.get("/connect")
def connect(user: User = Depends(require_roles(UserRole.admin))) -> dict[str, str]:
    settings = get_settings()
    if not settings.mercadolivre_client_id or not settings.mercadolivre_client_secret:
        raise HTTPException(status_code=503, detail="Credenciais do Mercado Livre não configuradas")
    now = datetime.now(UTC)
    state = jwt.encode(
        {"sub": user.id, "type": "ml_oauth", "iat": now, "exp": now + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.mercadolivre_client_id,
            "redirect_uri": str(settings.mercadolivre_redirect_uri),
            "state": state,
        }
    )
    return {"authorization_url": f"{settings.mercadolivre_auth_url}?{query}"}


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    try:
        payload = decode_token(state)
        if payload.get("type") != "ml_oauth":
            raise jwt.InvalidTokenError
        tokens = MercadoLivreClient(db).exchange_code(code)
        temporary = MarketplaceAccount(
            seller_id=str(tokens["user_id"]),
            encrypted_access_token=encrypt_secret(tokens["access_token"]),
            encrypted_refresh_token=(
                encrypt_secret(tokens["refresh_token"]) if tokens.get("refresh_token") else None
            ),
            token_expires_at=datetime.now(UTC)
            + timedelta(seconds=int(tokens.get("expires_in", 21600)) - 120),
        )
        profile_client = MercadoLivreClient(db, temporary)
        profile = profile_client.get("/users/me")
        if not isinstance(profile, dict):
            raise MercadoLivreError("Perfil inválido")
        account = (
            db.scalar(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.seller_id == temporary.seller_id
                )
            )
            or temporary
        )
        account.nickname = str(profile.get("nickname", "")) or None
        account.encrypted_access_token = temporary.encrypted_access_token
        account.encrypted_refresh_token = temporary.encrypted_refresh_token
        account.token_expires_at = temporary.token_expires_at
        account.active = True
        db.add(account)
        db.commit()
    except (jwt.PyJWTError, KeyError, MercadoLivreError):
        return RedirectResponse(f"{settings.frontend_url}/integrations?error=oauth")
    return RedirectResponse(f"{settings.frontend_url}/integrations?connected=true")


@router.get("/orders", response_model=list[MarketplaceOrderOut])
def orders(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[MarketplaceOrder]:
    return list(
        db.scalars(select(MarketplaceOrder).order_by(MarketplaceOrder.created_at.desc()).limit(200))
    )


@router.post("/webhook", status_code=202)
async def webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    topic = str(payload.get("topic", ""))
    resource = str(payload.get("resource", ""))
    seller_id = str(payload.get("user_id", ""))
    if (
        topic not in {"orders_v2", "invoices"}
        or not resource.startswith("/")
        or not seller_id.isdigit()
    ):
        raise HTTPException(status_code=400, detail="Notificação inválida")
    valid_resource = (
        bool(re.fullmatch(r"/orders/\d+", resource))
        if topic == "orders_v2"
        else resource.startswith(f"/users/{seller_id}/invoices/")
    )
    if not valid_resource:
        raise HTTPException(status_code=400, detail="Recurso de notificação inválido")
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("process_mercadolivre_notification", topic, resource, seller_id)
    await redis.close()
    return {"accepted": True}
