import asyncio
from datetime import UTC, date, datetime, timedelta

from app.api.routes import dashboard_marketplace_refresh as dashboard_route
from app.models import (
    AdDailyMetric,
    MarketplaceAccount,
    MarketplaceDashboardSync,
    Product,
    ProductMarketplaceListing,
)


def test_dashboard_refresh_retries_recent_partial_visit_coverage(db, monkeypatch):
    now = datetime.now(UTC)
    day = date.today()
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-partial-visits-refresh",
        active=True,
        encrypted_access_token="fake-token",
    )
    db.add(account)
    db.flush()
    for item_id in ("ITEM-COVERED", "ITEM-MISSING"):
        product = Product(
            sku=item_id,
            name=item_id,
            sale_price=10,
            cost_price=5,
            current_stock=1,
            minimum_stock=0,
        )
        db.add(product)
        db.flush()
        db.add(
            ProductMarketplaceListing(
                product_id=product.id,
                provider="mercadolivre",
                external_item_id=item_id,
                payload={"seller_id": account.seller_id},
            )
        )
    db.add(
        AdDailyMetric(
            account_id=account.id,
            channel="mercadolivre",
            item_id="ITEM-COVERED",
            metric_date=day,
            visits=3,
            sync_status="ok",
            synced_at=now,
        )
    )
    db.add(
        MarketplaceDashboardSync(
            account_id=account.id,
            period_start=day,
            period_end=day,
            sync_status="succeeded",
            partial=False,
            last_attempt_at=now,
            last_success_at=now,
        )
    )
    db.flush()

    class Queue:
        def __init__(self):
            self.jobs = {}

        async def enqueue_job(self, name, *args, **kwargs):
            job_id = kwargs["_job_id"]
            if job_id in self.jobs:
                return None
            self.jobs[job_id] = (name, args)
            return object()

    queue = Queue()

    async def get_queue():
        return queue

    monkeypatch.setattr(dashboard_route, "get_queue_pool", get_queue)
    result = asyncio.run(
        dashboard_route.refresh_marketplace_dashboard(
            start_date=day, end_date=day, force=False, db=db, _=None
        )
    )
    ad_jobs = [job for job in queue.jobs.values() if job[0] == "sync_mercadolivre_ad_metrics"]
    order_jobs = [
        job for job in queue.jobs.values() if job[0] == "sync_dashboard_marketplace_orders"
    ]
    assert result["status"] == "queued"
    assert len(ad_jobs) == 1
    assert order_jobs == []


def test_dashboard_refresh_requeues_stale_pending_job_once(db, monkeypatch):
    now = datetime.now(UTC)
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-stale-queue",
        active=True,
        encrypted_access_token="fake-token",
    )
    db.add(account)
    db.flush()
    db.add(
        MarketplaceDashboardSync(
            account_id=account.id,
            period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 18),
            sync_status="pending",
            partial=False,
            last_attempt_at=now - timedelta(minutes=10),
            last_success_at=now - timedelta(minutes=20),
        )
    )
    db.commit()

    class Queue:
        def __init__(self):
            self.jobs = {}

        async def enqueue_job(self, name, *args, **kwargs):
            job_id = kwargs["_job_id"]
            if job_id in self.jobs:
                return None
            self.jobs[job_id] = (name, args)
            return object()

    queue = Queue()

    async def get_queue():
        return queue

    monkeypatch.setattr(dashboard_route, "get_queue_pool", get_queue)

    async def refresh():
        return await dashboard_route.refresh_marketplace_dashboard(
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 18),
            force=False,
            db=db,
            _=None,
        )

    first = asyncio.run(refresh())
    second = asyncio.run(refresh())
    order_jobs = [
        (job_id, values)
        for job_id, values in queue.jobs.items()
        if values[0] == "sync_dashboard_marketplace_orders"
    ]
    assert first["status"] == "queued"
    assert second["status"] == "already_queued"
    assert len(order_jobs) == 1
    assert order_jobs[0][0].startswith(
        f"dashboard-ml-orders:{account.id}:2026-11-01:2026-11-18:"
    )
    state = db.query(MarketplaceDashboardSync).filter_by(account_id=account.id).one()
    assert state.sync_status == "pending"
    assert state.last_attempt_at.replace(tzinfo=UTC) > now - timedelta(minutes=5)
