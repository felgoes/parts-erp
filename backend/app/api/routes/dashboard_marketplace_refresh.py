from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.dashboard import _period
from app.core.permissions import Permission
from app.core.queue import get_queue_pool
from app.db.session import get_db
from app.models import AdDailyMetric, MarketplaceAccount, MarketplaceDashboardSync, User
from app.services.dashboard_marketplace import dashboard_marketplace_metrics

router = APIRouter(prefix="/dashboard", tags=["Painel"])


@router.get("/mercadolivre")
def marketplace_dashboard(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
):
    start, end, _, _ = _period(start_date, end_date)
    return dashboard_marketplace_metrics(db, start, end)


@router.post("/mercadolivre/refresh", status_code=202)
async def refresh_marketplace_dashboard(
    start_date: date = Query(...),
    end_date: date = Query(...),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    start, end, _, _ = _period(start_date, end_date)
    accounts = list(
        db.scalars(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "mercadolivre", MarketplaceAccount.active.is_(True)
            )
        )
    )
    if not accounts:
        return {"accepted": False, "status": "disconnected"}
    queue = await get_queue_pool()
    queued = 0
    now = datetime.now(UTC)
    for account in accounts:
        state = db.scalar(
            select(MarketplaceDashboardSync).where(
                MarketplaceDashboardSync.account_id == account.id,
                MarketplaceDashboardSync.period_start == start,
                MarketplaceDashboardSync.period_end == end,
            )
        )
        created = state is None
        if created:
            state = MarketplaceDashboardSync(
                account_id=account.id,
                period_start=start,
                period_end=end,
                sync_status="pending",
                partial=False,
                last_attempt_at=now,
            )
            db.add(state)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                state = db.scalar(
                    select(MarketplaceDashboardSync).where(
                        MarketplaceDashboardSync.account_id == account.id,
                        MarketplaceDashboardSync.period_start == start,
                        MarketplaceDashboardSync.period_end == end,
                    )
                )
                if state is None:
                    raise
                created = False

        last_attempt = state.last_attempt_at
        if last_attempt and last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=UTC)
        active_recent = (
            state.sync_status in {"pending", "running"}
            and last_attempt is not None
            and now - last_attempt < timedelta(minutes=5)
        )
        last_success = state.last_success_at
        if last_success and last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
        fresh = (
            state.sync_status == "succeeded"
            and not state.partial
            and last_success is not None
            and now - last_success < timedelta(minutes=5)
        )
        recent_attempt = last_attempt is not None and now - last_attempt < timedelta(minutes=5)
        order_due = created or (
            not active_recent
            and not fresh
            and (force or not recent_attempt)
        )
        if order_due and not created:
            state.sync_status, state.sync_error, state.partial = "pending", None, False
            state.last_attempt_at = now
            db.commit()
        if order_due:
            job = await queue.enqueue_job(
                "sync_dashboard_marketplace_orders",
                account.id,
                start.isoformat(),
                end.isoformat(),
                _job_id=(
                    f"dashboard-ml-orders:{account.id}:{start.isoformat()}:"
                    f"{end.isoformat()}:{uuid4().hex}"
                ),
            )
            if job:
                queued += 1

        latest_metric = db.scalar(
            select(func.max(AdDailyMetric.synced_at)).where(
                AdDailyMetric.account_id == account.id, AdDailyMetric.channel == "mercadolivre"
            )
        )
        metric_at = (
            latest_metric.replace(tzinfo=UTC)
            if latest_metric and latest_metric.tzinfo is None
            else latest_metric
        )
        visit_metrics = dashboard_marketplace_metrics(db, start, end)["metrics"]["visits"]
        coverage_incomplete = visit_metrics["state"] == "partial"
        if (
            metric_at is None
            or now - metric_at >= timedelta(hours=6)
            or force
            or coverage_incomplete
        ):
            # ARQ retains completed job IDs. A short time bucket deduplicates concurrent
            # page loads while allowing a later retry after an earlier visit API failure.
            job = await queue.enqueue_job(
                "sync_mercadolivre_ad_metrics",
                account.id,
                _job_id=f"ad-metrics:{account.id}:{int(now.timestamp() // 300)}",
            )
            if job:
                queued += 1
    return {"accepted": True, "status": "queued" if queued else "already_queued"}
