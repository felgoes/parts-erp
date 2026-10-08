import asyncio
import threading
from datetime import UTC, datetime

from app.workers import settings as worker_settings
from app.models import ErpSettings


def test_scheduled_backup_catches_up_after_configured_local_time():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_at=datetime(2026, 10, 7, 5, 0, tzinfo=UTC),
    )

    # 06:15 UTC is 03:15 in São Paulo: the exact 02:00 minute has passed,
    # but the daily backup must still run once for the local calendar date.
    assert worker_settings._scheduled_backup_is_due(
        settings, datetime(2026, 10, 8, 6, 15, tzinfo=UTC)
    ) is True
    assert worker_settings._scheduled_backup_is_due(
        settings, datetime(2026, 10, 8, 6, 16, tzinfo=UTC)
    ) is True


def test_scheduled_backup_does_not_repeat_same_local_day():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_at=datetime(2026, 10, 8, 5, 10, tzinfo=UTC),
    )

    assert worker_settings._scheduled_backup_is_due(
        settings, datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
    ) is False


def test_scheduled_backup_waits_until_local_time():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
    )

    # 04:59 UTC is 01:59 in São Paulo.
    assert worker_settings._scheduled_backup_is_due(
        settings, datetime(2026, 10, 8, 4, 59, tzinfo=UTC)
    ) is False


def test_marketplace_webhook_work_runs_outside_worker_event_loop(monkeypatch):
    event_loop_thread = threading.get_ident()
    execution_threads = []
    monkeypatch.setattr(
        worker_settings,
        "_process_mercadolivre_notification",
        lambda *args: execution_threads.append(threading.get_ident()),
    )

    asyncio.run(
        worker_settings.process_mercadolivre_notification(
            {}, "shipments", "/shipments/555", "77"
        )
    )

    assert execution_threads
    assert execution_threads[0] != event_loop_thread


def test_order_webhook_reaches_sync_with_runtime_clock(db, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from app.models import MarketplaceAccount

    db.add(MarketplaceAccount(provider="mercadolivre", seller_id="77", active=True, encrypted_access_token="mock"))
    db.commit()
    synced = []
    monkeypatch.setattr(worker_settings, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(
        worker_settings.MercadoLivreClient, "get", lambda self, resource: {"id": "123"}
    )
    monkeypatch.setattr(
        worker_settings, "sync_order",
        lambda db, seller, resource: (
            synced.append((seller, resource))
            or SimpleNamespace(invoice_id=None, sync_status="synced")
        ),
    )
    worker_settings._process_mercadolivre_notification("orders_v2", "/orders/123", "77")
    assert synced == [("77", "/orders/123")]
