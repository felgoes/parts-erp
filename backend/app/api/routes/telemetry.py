from collections import defaultdict, deque
from datetime import UTC, date, datetime, time, timedelta, timezone
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.config import get_settings
from app.core.permissions import Permission
from app.core.queue import get_queue_pool
from app.db.session import get_db
from app.models import HealthSnapshot, MarketplaceAccount, Product, TelemetryEvent, User
from app.schemas.common import (
    EventCount,
    ProductViewCount,
    TelemetryDailyCount,
    TelemetryEventCreate,
    TelemetryHealthOut,
    TelemetrySummary,
)
from app.services.ad_performance import ad_performance_summary

router = APIRouter(prefix="/telemetry", tags=["Monitoramento"])

ALLOWED_EVENTS = {
    "landing_view",
    "catalog_search",
    "product_view",
    "mercado_livre_click",
    "whatsapp_click",
    "catalog_empty_result",
    "library_vehicle_view",
    "library_part_view",
    "library_reference_copy",
}
ALLOWED_PROPERTIES = {"sku", "provider", "external_item_id", "listing_id", "placement", "brand", "model", "year", "source", "campaign", "vehicle_id", "part_id", "entry_source"}
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _enforce_rate_limit(key: str, limit: int) -> None:
    now = monotonic()
    with _rate_lock:
        window = _rate_windows[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Muitos eventos; tente novamente em instantes",
            )
        window.append(now)


def _safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in properties.items():
        if key not in ALLOWED_PROPERTIES:
            continue
        if key == "entry_source" and value not in {"menu", "direct", "internal"}:
            continue
        if isinstance(value, (str, int, float, bool)) and len(str(value)) <= 120:
            clean[key] = value
    return clean


@router.post("/events", status_code=202)
def collect_event(
    payload: TelemetryEventCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.name not in ALLOWED_EVENTS:
        raise HTTPException(status_code=422, detail="Evento nao permitido")
    settings = get_settings()
    anonymous_id = payload.anonymous_id or ""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    client_ip = (forwarded or (request.client.host if request.client else "unknown")).split(",")[0]
    _enforce_rate_limit(
        sha256(f"{client_ip}:{anonymous_id}".encode()).hexdigest(),
        settings.telemetry_rate_limit_per_minute,
    )
    visitor_hash = (
        sha256(f"{settings.secret_key.get_secret_value()}:{anonymous_id}".encode()).hexdigest()
        if anonymous_id
        else None
    )
    db.add(
        TelemetryEvent(
            name=payload.name,
            source=payload.source,
            visitor_hash=visitor_hash,
            properties=_safe_properties(payload.properties),
        )
    )
    db.commit()
    return {"status": "accepted"}


@router.get("/summary", response_model=TelemetrySummary)
def summary(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MONITORING_READ)),
) -> TelemetrySummary:
    today = datetime.now(UTC).date()
    start = start_date or (today - timedelta(days=days - 1))
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if (end - start).days > 364:
        raise HTTPException(status_code=422, detail="O período máximo é de 365 dias")
    # Brazil currently observes UTC-03 year-round; using a fixed offset keeps
    # the monitor working on minimal Termux installs without the tzdata package.
    local_zone = timezone(timedelta(hours=-3))
    since = datetime.combine(start, time.min, local_zone).astimezone(UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, local_zone).astimezone(UTC)
    rows = db.execute(
        select(TelemetryEvent.name, func.count(TelemetryEvent.id))
        .where(TelemetryEvent.created_at >= since)
        .where(TelemetryEvent.created_at < until)
        .group_by(TelemetryEvent.name)
        .order_by(func.count(TelemetryEvent.id).desc())
    ).all()
    counts = [EventCount(name=name, count=count) for name, count in rows]
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        local_event_date = func.date(TelemetryEvent.created_at, "-3 hours")
    else:
        local_event_date = func.date(func.timezone("America/Sao_Paulo", TelemetryEvent.created_at))
    daily_rows = db.execute(
        select(local_event_date, TelemetryEvent.name, func.count(TelemetryEvent.id))
        .where(TelemetryEvent.created_at >= since)
        .where(TelemetryEvent.created_at < until)
        .group_by(local_event_date, TelemetryEvent.name)
        .order_by(local_event_date)
    ).all()
    daily_counts: dict[date, list[EventCount]] = defaultdict(list)
    for event_date, name, count in daily_rows:
        parsed_date = (
            event_date if isinstance(event_date, date) else date.fromisoformat(str(event_date))
        )
        daily_counts[parsed_date].append(EventCount(name=name, count=count))
    daily_events = [
        TelemetryDailyCount(date=day, events=daily_counts.get(day, []))
        for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    ]
    sku_expression = TelemetryEvent.properties["sku"].as_string()
    view_rows = db.execute(
        select(sku_expression, Product.name, func.count(TelemetryEvent.id))
        .select_from(TelemetryEvent)
        .outerjoin(Product, Product.sku == sku_expression)
        .where(TelemetryEvent.name == "product_view")
        .where(TelemetryEvent.created_at >= since)
        .where(TelemetryEvent.created_at < until)
        .where(sku_expression.is_not(None))
        .group_by(sku_expression, Product.name)
        .order_by(func.count(TelemetryEvent.id).desc())
    ).all()
    product_views = [
        ProductViewCount(sku=sku, product_name=product_name or sku, views=count)
        for sku, product_name, count in view_rows
        if sku
    ]
    health = list(
        db.scalars(select(HealthSnapshot).order_by(HealthSnapshot.checked_at.desc()).limit(20))
    )
    return TelemetrySummary(
        days=(end - start).days + 1,
        events=counts,
        daily_events=daily_events,
        product_views=product_views,
        health=health,
    )


@router.get("/health", response_model=list[TelemetryHealthOut])
def health(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MONITORING_READ)),
) -> list[TelemetryHealthOut]:
    return list(
        db.scalars(select(HealthSnapshot).order_by(HealthSnapshot.checked_at.desc()).limit(50))
    )


@router.get("/ad-performance")
def ad_performance(
    start_date: date = Query(...),
    end_date: date = Query(...),
    channel: str | None = Query(default=None, max_length=30),
    status: str | None = Query(default=None, max_length=40),
    search: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort_by: str = Query(default="visits", pattern="^(title|status|visits|orders|conversion)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MONITORING_READ)),
) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=-3))).date()
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if end_date > today:
        raise HTTPException(status_code=422, detail="A data final não pode estar no futuro")
    if (end_date - start_date).days > 149:
        raise HTTPException(status_code=422, detail="O período máximo é de 150 dias")
    return ad_performance_summary(
        db,
        start=start_date,
        end=end_date,
        channel=channel,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


@router.post("/ad-performance/refresh", status_code=202)
async def refresh_ad_performance(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MONITORING_READ)),
) -> dict[str, str | bool]:
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.active.is_(True), MarketplaceAccount.provider == "mercadolivre"
        )
    )
    if not account:
        raise HTTPException(
            status_code=409, detail="Conecte uma conta do Mercado Livre para atualizar os anúncios"
        )
    queue = await get_queue_pool()
    job = await queue.enqueue_job(
        "sync_mercadolivre_ad_metrics", account.id, _job_id=f"ad-metrics:{account.id}"
    )
    return {"accepted": True, "status": "queued" if job else "already_queued"}
