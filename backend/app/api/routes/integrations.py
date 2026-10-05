import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import jwt
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.config import get_settings
from app.core.permissions import Permission
from app.core.security import decode_token, encrypt_secret
from app.db.session import get_db
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.shopee.client import ShopeeClient, ShopeeError
from app.models import (
    MarketplaceAccount,
    MarketplaceConfig,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    ShopeeConfig,
    User,
)
from app.schemas.common import (
    MarketplaceConfigOut,
    MarketplaceConfigUpdate,
    MarketplaceOrderEventOut,
    MarketplaceOrderOut,
    MarketplaceStatus,
    ShopeeConfigOut,
    ShopeeConfigUpdate,
    ShopeeStatus,
)

router = APIRouter(prefix="/integrations/mercadolivre", tags=["Mercado Livre"])
shopee_router = APIRouter(prefix="/integrations/shopee", tags=["Shopee"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=MarketplaceStatus)
def status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_STATUS)),
) -> MarketplaceStatus:
    settings = get_settings()
    config = db.scalar(select(MarketplaceConfig).limit(1))
    account = db.scalar(
        select(MarketplaceAccount).where(MarketplaceAccount.active.is_(True)).limit(1)
    )
    return MarketplaceStatus(
        configured=bool(
            (config.client_id if config else settings.mercadolivre_client_id)
            and (config.encrypted_client_secret if config else settings.mercadolivre_client_secret)
        ),
        connected=account is not None,
        seller_id=account.seller_id if account else None,
        nickname=account.nickname if account else None,
        token_expires_at=account.token_expires_at if account else None,
    )


@router.get("/config", response_model=MarketplaceConfigOut)
def get_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> MarketplaceConfigOut:
    settings = get_settings()
    config = db.scalar(select(MarketplaceConfig).limit(1))
    return MarketplaceConfigOut(
        client_id=config.client_id if config else settings.mercadolivre_client_id,
        client_secret_configured=bool(config.encrypted_client_secret)
        if config
        else bool(settings.mercadolivre_client_secret),
        redirect_uri=(config.redirect_uri if config else None)
        or str(settings.mercadolivre_redirect_uri),
        site_id=config.site_id if config else settings.mercadolivre_site_id,
        import_orders=config.import_orders if config else True,
        automatic_stock=config.automatic_stock if config else True,
        sync_documents=config.sync_documents if config else True,
    )


@router.put("/config", response_model=MarketplaceConfigOut)
def update_config(
    payload: MarketplaceConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> MarketplaceConfigOut:
    settings = get_settings()
    config = db.scalar(select(MarketplaceConfig).limit(1)) or MarketplaceConfig()
    config.client_id = payload.client_id.strip()
    if payload.client_secret:
        config.encrypted_client_secret = encrypt_secret(payload.client_secret)
    elif not config.encrypted_client_secret and settings.mercadolivre_client_secret:
        config.encrypted_client_secret = encrypt_secret(
            settings.mercadolivre_client_secret.get_secret_value()
        )
    config.redirect_uri = payload.redirect_uri.strip()
    config.site_id = payload.site_id.strip()
    config.import_orders = payload.import_orders
    config.automatic_stock = payload.automatic_stock
    config.sync_documents = payload.sync_documents
    db.add(config)
    db.commit()
    return get_config(db, _)


@router.get("/connect")
def connect(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> dict[str, str]:
    settings = get_settings()
    config = db.scalar(select(MarketplaceConfig).limit(1))
    client_id = config.client_id if config else settings.mercadolivre_client_id
    configured_secret = (
        config.encrypted_client_secret if config else settings.mercadolivre_client_secret
    )
    if not client_id or not configured_secret:
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
            "client_id": client_id,
            "redirect_uri": (config.redirect_uri if config else None)
            or str(settings.mercadolivre_redirect_uri),
            "state": state,
        }
    )
    return {"authorization_url": f"{settings.mercadolivre_auth_url}?{query}"}


@router.get("/callback")
async def callback(code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
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
        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await redis.enqueue_job("sync_mercadolivre_account", account.seller_id)
            await redis.close()
        except Exception:
            # A conexao nao deve impedir a conclusao do OAuth; o worker pode ser reexecutado.
            logger.warning("OAuth concluído, mas a sincronização inicial não entrou na fila.")
    except (jwt.PyJWTError, KeyError, MercadoLivreError):
        return RedirectResponse(f"{settings.frontend_url}/integrations?error=oauth")
    return RedirectResponse(f"{settings.frontend_url}/integrations?connected=true")


@router.get("/orders", response_model=list[MarketplaceOrderOut])
def orders(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
) -> list[MarketplaceOrder]:
    return list(
        db.scalars(
            select(MarketplaceOrder)
            .options(selectinload(MarketplaceOrder.invoice))
            .order_by(MarketplaceOrder.created_at.desc())
            .limit(200)
        )
    )


@router.get("/orders/{order_id}", response_model=MarketplaceOrderOut)
def order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
) -> MarketplaceOrder:
    order = db.scalar(
        select(MarketplaceOrder)
        .options(selectinload(MarketplaceOrder.invoice))
        .where(MarketplaceOrder.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.get("/orders/{order_id}/history", response_model=list[MarketplaceOrderEventOut])
def order_history(
    order_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
) -> list[MarketplaceOrderEvent]:
    if not db.get(MarketplaceOrder, order_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return list(
        db.scalars(
            select(MarketplaceOrderEvent)
            .where(MarketplaceOrderEvent.order_id == order_id)
            .order_by(MarketplaceOrderEvent.created_at.asc())
        )
    )


@router.post("/orders/{order_id}/automate", response_model=MarketplaceOrderOut)
def automate_order(
    order_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
) -> MarketplaceOrder:
    from app.integrations.mercadolivre.sync import automate_order_documents

    order = db.get(MarketplaceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not order.invoice_id:
        return order
    return automate_order_documents(db, order)


@router.post("/sync", status_code=202)
async def sync_now(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
) -> dict[str, bool | str]:
    """Queue a full Mercado Livre import for the connected seller account."""
    account = db.scalar(
        select(MarketplaceAccount)
        .where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.active.is_(True),
        )
        .limit(1)
    )
    if not account:
        raise HTTPException(status_code=409, detail="Conta do Mercado Livre não conectada")
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("sync_mercadolivre_account", account.seller_id)
    await redis.close()
    return {"accepted": True, "message": "Sincronização do Mercado Livre enfileirada"}


@router.post("/webhook", status_code=202)
@router.post("/notifications", status_code=202)
async def webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    topic = str(payload.get("topic", ""))
    resource = str(payload.get("resource", ""))
    seller_id = str(payload.get("user_id", ""))
    if (
        topic not in {"orders_v2", "shipments", "payments", "invoices", "claims", "returns"}
        or not resource.startswith("/")
        or not seller_id.isdigit()
    ):
        raise HTTPException(status_code=400, detail="Notificação inválida")
    valid_resource = (
        bool(re.fullmatch(r"/orders/\d+", resource))
        if topic == "orders_v2"
        else (
            resource.startswith(f"/users/{seller_id}/invoices/")
            if topic == "invoices"
            else bool(re.fullmatch(r"/(shipments|collections|claims|returns)/\d+", resource))
        )
    )
    if not valid_resource:
        raise HTTPException(status_code=400, detail="Recurso de notificação inválido")
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("process_mercadolivre_notification", topic, resource, seller_id)
    await redis.close()
    return {"accepted": True}


@shopee_router.get("/status", response_model=ShopeeStatus)
def shopee_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_STATUS)),
) -> ShopeeStatus:
    settings = get_settings()
    config = db.scalar(select(ShopeeConfig).limit(1))
    account = db.scalar(
        select(MarketplaceAccount)
        .where(
            MarketplaceAccount.provider == "shopee",
            MarketplaceAccount.active.is_(True),
        )
        .limit(1)
    )
    return ShopeeStatus(
        configured=bool(
            (config.partner_id if config else settings.shopee_partner_id)
            and (config.encrypted_partner_key if config else settings.shopee_partner_key)
        ),
        connected=account is not None,
        shop_id=account.seller_id if account else (config.shop_id if config else None),
        token_expires_at=account.token_expires_at if account else None,
    )


@shopee_router.get("/config", response_model=ShopeeConfigOut)
def shopee_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> ShopeeConfigOut:
    settings = get_settings()
    config = db.scalar(select(ShopeeConfig).limit(1))
    return ShopeeConfigOut(
        partner_id=config.partner_id if config else settings.shopee_partner_id,
        partner_key_configured=bool(config.encrypted_partner_key)
        if config
        else bool(settings.shopee_partner_key),
        shop_id=config.shop_id if config else None,
        redirect_uri=(config.redirect_uri if config else None) or str(settings.shopee_redirect_uri),
        region=config.region if config else "BR",
        import_orders=config.import_orders if config else True,
        automatic_stock=config.automatic_stock if config else True,
        sync_documents=config.sync_documents if config else True,
    )


@shopee_router.put("/config", response_model=ShopeeConfigOut)
def update_shopee_config(
    payload: ShopeeConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> ShopeeConfigOut:
    settings = get_settings()
    config = db.scalar(select(ShopeeConfig).limit(1)) or ShopeeConfig()
    config.partner_id = payload.partner_id.strip()
    if payload.partner_key:
        config.encrypted_partner_key = encrypt_secret(payload.partner_key)
    elif not config.encrypted_partner_key and settings.shopee_partner_key:
        config.encrypted_partner_key = encrypt_secret(
            settings.shopee_partner_key.get_secret_value()
        )
    config.shop_id = payload.shop_id.strip() if payload.shop_id else None
    config.redirect_uri = payload.redirect_uri.strip()
    config.region = payload.region.strip().upper()
    config.import_orders = payload.import_orders
    config.automatic_stock = payload.automatic_stock
    config.sync_documents = payload.sync_documents
    db.add(config)
    db.commit()
    return shopee_config(db, _)


@shopee_router.get("/connect")
def connect_shopee(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.INTEGRATION_CONFIG)),
) -> JSONResponse:
    settings = get_settings()
    config = db.scalar(select(ShopeeConfig).limit(1))
    partner_id = config.partner_id if config else settings.shopee_partner_id
    partner_key = config.encrypted_partner_key if config else settings.shopee_partner_key
    if not partner_id or not partner_key:
        raise HTTPException(status_code=503, detail="Credenciais da Shopee não configuradas")
    now = datetime.now(UTC)
    state = jwt.encode(
        {"sub": user.id, "type": "shopee_oauth", "iat": now, "exp": now + timedelta(minutes=10)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    redirect_uri = (config.redirect_uri if config else None) or str(settings.shopee_redirect_uri)
    key = (
        partner_key.get_secret_value() if hasattr(partner_key, "get_secret_value") else partner_key
    )
    response = JSONResponse(
        {"authorization_url": ShopeeClient(partner_id, key).authorization_url(redirect_uri)}
    )
    response.set_cookie(
        "shopee_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=redirect_uri.startswith("https://"),
        samesite="lax",
    )
    return response


@shopee_router.get("/callback")
async def shopee_callback(
    request: Request,
    code: str,
    shop_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    try:
        state = request.cookies.get("shopee_oauth_state")
        if not state:
            raise jwt.InvalidTokenError
        payload = decode_token(state)
        if payload.get("type") != "shopee_oauth":
            raise jwt.InvalidTokenError
        config = db.scalar(select(ShopeeConfig).limit(1))
        partner_id = config.partner_id if config else settings.shopee_partner_id
        encrypted_key = config.encrypted_partner_key if config else settings.shopee_partner_key
        key = (
            encrypted_key.get_secret_value()
            if hasattr(encrypted_key, "get_secret_value")
            else encrypted_key
        )
        if not partner_id or not key:
            raise ShopeeError("Shopee não configurada")
        tokens = ShopeeClient(partner_id, key).exchange_code(code, shop_id)
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "shopee",
                MarketplaceAccount.seller_id == str(shop_id),
            )
        ) or MarketplaceAccount(provider="shopee", seller_id=str(shop_id))
        account.encrypted_access_token = encrypt_secret(tokens["access_token"])
        account.encrypted_refresh_token = (
            encrypt_secret(tokens["refresh_token"]) if tokens.get("refresh_token") else None
        )
        account.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens.get("expire_in", 14400)) - 120
        )
        account.active = True
        db.add(account)
        if config:
            config.shop_id = str(shop_id)
        db.commit()
        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await redis.enqueue_job("sync_shopee_account", str(shop_id))
            await redis.close()
        except Exception:
            logger.warning("OAuth concluído, mas a sincronização inicial não entrou na fila.")
    except (jwt.PyJWTError, KeyError, ShopeeError, ValueError):
        response = RedirectResponse(f"{settings.frontend_url}/integrations?error=shopee_oauth")
        response.delete_cookie("shopee_oauth_state")
        return response
    response = RedirectResponse(f"{settings.frontend_url}/integrations?shopee_connected=true")
    response.delete_cookie("shopee_oauth_state")
    return response


@shopee_router.post("/webhook", status_code=202)
async def shopee_webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Notificacao Shopee invalida")
    shop_id = str(payload.get("shop_id") or payload.get("shopid") or "")
    if not shop_id:
        raise HTTPException(status_code=400, detail="Loja Shopee ausente")
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("process_shopee_notification", payload)
    await redis.close()
    return {"accepted": True}
