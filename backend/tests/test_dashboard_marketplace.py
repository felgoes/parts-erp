import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from app.api.routes import dashboard_marketplace_refresh as dashboard_route
from app.models import (
    AdDailyMetric,
    MarketplaceAccount,
    MarketplaceDashboardSync,
    MarketplaceOrder,
    Product,
    ProductMarketplaceListing,
)
from app.services import dashboard_marketplace as service
from app.services import dashboard_marketplace_sync as sync_service


def dashboard_fixture(db):
    day = date(2026, 11, 19)
    now = datetime(2026, 11, 19, 15, tzinfo=UTC)
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-seller-board",
        active=True,
        encrypted_access_token="fake-token",
    )
    db.add(account)
    db.flush()
    products = {}
    for sku in "ABCDEF":
        product = Product(
            sku=sku,
            name=f"Produto {sku}",
            sale_price=Decimal("100"),
            cost_price=Decimal("50"),
            current_stock=Decimal("10"),
            minimum_stock=Decimal("1"),
        )
        db.add(product)
        db.flush()
        products[sku] = product
        db.add(
            ProductMarketplaceListing(
                product_id=product.id,
                provider="mercadolivre",
                external_item_id=f"ITEM-{sku}",
                title=f"Anúncio {sku}",
                payload={"seller_id": account.seller_id},
            )
        )
        db.add(
            AdDailyMetric(
                account_id=account.id,
                channel="mercadolivre",
                item_id=f"ITEM-{sku}",
                metric_date=day,
                visits=20,
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
            last_success_at=now,
            last_attempt_at=now,
        )
    )
    orders = [
        ("ML-01", [("A", 2, 100), ("B", 1, 50)]),
        ("ML-02", [("C", 1, 80), ("D", 3, 20)]),
        ("ML-03", [("A", 1, 100), ("E", 2, 30), ("F", 1, 15)]),
    ]
    for order_id, lines in orders:
        payload_lines = [
            {
                "item": {"id": f"ITEM-{sku}", "title": f"Anúncio {sku}"},
                "quantity": qty,
                "unit_price": price,
                "currency_id": "BRL",
            }
            for sku, qty, price in lines
        ]
        db.add(
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id=order_id,
                seller_id=account.seller_id,
                status="paid",
                sync_status="synced",
                created_at=now,
                payload={
                    "id": order_id,
                    "status": "paid",
                    "currency_id": "BRL",
                    "payments": [{"status": "approved"}],
                    "order_items": payload_lines,
                },
            )
        )
    db.flush()
    return account, day


def test_dashboard_marketplace_matches_spec_mass(db):
    _, day = dashboard_fixture(db)
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["orders"]["value"] == 3
    assert data["metrics"]["units"]["value"] == Decimal("11")
    assert data["metrics"]["gross"]["value"] == "565"
    assert data["metrics"]["average_ticket"]["value"] == "188.33"
    assert data["metrics"]["visits"]["value"] == 120
    assert data["metrics"]["conversion"]["value"] == "2.50"
    assert [(row["sku"], row["units"]) for row in data["products"]] == [
        ("A", "3"),
        ("D", "3"),
        ("E", "2"),
        ("B", "1"),
        ("C", "1"),
    ]
    assert data["last_synced_at"] is not None


def test_dashboard_marketplace_excludes_manual_and_cancelled_orders(db):
    account, day = dashboard_fixture(db)
    now = datetime(2026, 11, 19, 15, tzinfo=UTC)
    db.add_all(
        [
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id="CANCEL-1",
                seller_id=account.seller_id,
                status="cancelled",
                sync_status="synced",
                created_at=now,
                payload={
                    "status": "cancelled",
                    "order_items": [
                        {
                            "item": {"id": "ITEM-A"},
                            "quantity": 1,
                            "unit_price": 100,
                            "currency_id": "BRL",
                        }
                    ],
                },
            ),
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id="PENDING-1",
                seller_id=account.seller_id,
                status="payment_in_process",
                sync_status="synced",
                created_at=now,
                payload={
                    "status": "payment_in_process",
                    "payments": [{"status": "pending"}],
                    "order_items": [
                        {
                            "item": {"id": "ITEM-A"},
                            "quantity": 1,
                            "unit_price": 100,
                            "currency_id": "BRL",
                        }
                    ],
                },
            ),
        ]
    )
    db.flush()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["orders"]["value"] == 3
    assert data["metrics"]["gross"]["value"] == "565"


def test_visits_zero_missing_partial_and_conversion_states(db):
    account, day = dashboard_fixture(db)
    rows = list(db.query(AdDailyMetric).filter_by(account_id=account.id))
    for row in rows:
        row.visits = 0
    db.flush()
    zero = service.dashboard_marketplace_metrics(db, day, day)
    assert zero["metrics"]["visits"]["value"] == 0
    assert zero["metrics"]["conversion"]["value"] is None

    for row in rows:
        db.delete(row)
    db.flush()
    missing = service.dashboard_marketplace_metrics(db, day, day)
    assert missing["metrics"]["visits"]["value"] is None
    assert missing["metrics"]["visits"]["state"] == "partial"
    assert missing["metrics"]["conversion"]["value"] is None


def test_dashboard_failure_preserves_known_values_as_partial(db):
    account, day = dashboard_fixture(db)
    state = db.query(MarketplaceDashboardSync).filter_by(account_id=account.id).one()
    state.sync_status = "failed"
    state.sync_error = "QA failure"
    db.flush()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["orders"]["value"] == 3
    assert data["metrics"]["orders"]["state"] == "partial"
    assert data["last_synced_at"] is not None


def test_order_window_sync_deduplicates_ids_and_marks_unstable_page_partial(db, monkeypatch):
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-scan",
        active=True,
        encrypted_access_token="fake",
    )
    db.add(account)
    db.flush()
    calls = []

    class Client:
        def __init__(self, *_args):
            pass

        def get(self, path):
            calls.append(path)
            offset = int(parse_qs(urlparse(path).query)["offset"][0])
            if offset == 0:
                return {"paging": {"total": 2, "limit": 1}, "results": [{"id": "100"}]}
            return {"paging": {"total": 2, "limit": 1}, "results": [{"id": "100"}]}

    synced = []
    monkeypatch.setattr(sync_service, "MercadoLivreClient", Client)
    monkeypatch.setattr(sync_service, "sync_order", lambda *_args: synced.append("100"))
    count = sync_service.sync_dashboard_orders_for_period(
        db, account, date(2026, 11, 19), date(2026, 11, 19)
    )
    state = db.query(MarketplaceDashboardSync).filter_by(account_id=account.id).one()
    assert count == 1
    assert synced == ["100"]
    assert state.sync_status == "succeeded"
    assert state.partial is True


def test_no_orders_has_zero_sales_but_no_average_ticket(db):
    account, day = dashboard_fixture(db)
    db.query(MarketplaceOrder).filter_by(seller_id=account.seller_id).delete()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["orders"]["value"] == 0
    assert data["metrics"]["units"]["value"] == Decimal("0")
    assert data["metrics"]["gross"]["value"] == "0"
    assert data["metrics"]["average_ticket"]["value"] is None
    assert data["metrics"]["conversion"]["value"] == "0.00"
    assert data["products"] == []
    assert data["products_state"] == "empty"


def test_partial_visits_keep_known_subtotal_without_conversion(db):
    account, day = dashboard_fixture(db)
    rows = list(db.query(AdDailyMetric).filter_by(account_id=account.id))
    for row in rows[:3]:
        row.visits = 30
    for row in rows[3:]:
        db.delete(row)
    db.flush()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["visits"]["value"] == 90
    assert data["metrics"]["visits"]["state"] == "partial"
    assert data["metrics"]["conversion"]["value"] is None


def test_missing_order_line_price_keeps_units_and_partial_gross(db):
    account, day = dashboard_fixture(db)
    order = db.query(MarketplaceOrder).filter_by(external_order_id="ML-01").one()
    order.payload["order_items"][0].pop("unit_price")
    db.flush()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["units"]["value"] == Decimal("11")
    assert data["metrics"]["gross"]["value"] == "365"
    assert data["metrics"]["gross"]["state"] == "partial"
    assert data["metrics"]["average_ticket"]["value"] is None


def test_today_filters_marketplace_orders_at_sao_paulo_midnight(db):
    account, day = dashboard_fixture(db)
    base = {
        "status": "paid",
        "payments": [{"status": "approved"}],
        "order_items": [
            {"item": {"id": "ITEM-A"}, "quantity": 1, "unit_price": 10, "currency_id": "BRL"}
        ],
    }
    for order_id, created in [
        ("BEFORE-SP-DAY", datetime(2026, 11, 19, 2, 59, tzinfo=UTC)),
        ("AT-SP-DAY", datetime(2026, 11, 19, 3, 0, tzinfo=UTC)),
    ]:
        db.add(
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id=order_id,
                seller_id=account.seller_id,
                status="paid",
                sync_status="synced",
                created_at=created,
                payload={**base, "id": order_id},
            )
        )
    db.flush()
    data = service.dashboard_marketplace_metrics(db, day, day)
    assert data["metrics"]["orders"]["value"] == 4


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
