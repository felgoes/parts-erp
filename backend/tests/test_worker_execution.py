import asyncio
import threading
from datetime import UTC, datetime

from app.models import ErpSettings
from app.workers import settings as worker_settings


def test_vehicle_fleet_refresh_is_scheduled_on_startup_and_daily():
    fleet_job = next(
        job
        for job in worker_settings.WorkerSettings.cron_jobs
        if job.name == "refresh-vehicle-market-fleet"
    )

    assert fleet_job.run_at_startup is True
    assert fleet_job.hour == 6
    assert fleet_job.minute == 20


def test_scheduled_backup_catches_up_after_configured_local_time():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_at=datetime(2026, 10, 7, 5, 0, tzinfo=UTC),
    )

    # 06:15 UTC is 03:15 in São Paulo: the exact 02:00 minute has passed,
    # but the daily backup must still run once for the local calendar date.
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 6, 15, tzinfo=UTC))
        is True
    )
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 6, 16, tzinfo=UTC))
        is True
    )


def test_scheduled_backup_does_not_repeat_after_success_in_the_same_window():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_at=datetime(2026, 10, 8, 5, 10, tzinfo=UTC),
        backup_last_status="success",
    )

    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 8, 0, tzinfo=UTC))
        is False
    )


def test_failed_backup_waits_for_the_controlled_interval():
    attempt = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_status="failed",
        backup_last_at=attempt,
        backup_last_attempt_at=attempt,
        backup_attempts_date="2026-10-08",
        backup_attempts_today=1,
    )

    # 05:29 UTC é 02:29 em São Paulo: menos de 30 minutos depois da falha.
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 5, 29, tzinfo=UTC))
        is False
    )
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 5, 31, tzinfo=UTC))
        is True
    )


def test_failed_backup_stops_after_the_window_attempt_limit():
    attempt = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
        backup_last_status="failed",
        backup_last_at=attempt,
        backup_last_attempt_at=attempt,
        backup_attempts_date="2026-10-08",
        backup_attempts_today=4,
    )

    # Já tentou quatro vezes nesta janela: não insiste mais hoje, nem horas depois.
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 15, 0, tzinfo=UTC))
        is False
    )
    # No dia seguinte a janela reinicia.
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 9, 6, 0, tzinfo=UTC))
        is True
    )


def test_scheduled_backup_waits_until_local_time():
    settings = ErpSettings(
        backup_enabled=True,
        backup_frequency="daily",
        backup_time="02:00",
    )

    # 04:59 UTC is 01:59 in São Paulo.
    assert (
        worker_settings._scheduled_backup_is_due(settings, datetime(2026, 10, 8, 4, 59, tzinfo=UTC))
        is False
    )


def test_marketplace_webhook_work_runs_outside_worker_event_loop(monkeypatch):
    event_loop_thread = threading.get_ident()
    execution_threads = []
    monkeypatch.setattr(
        worker_settings,
        "_process_mercadolivre_notification",
        lambda *args: execution_threads.append(threading.get_ident()),
    )

    asyncio.run(
        worker_settings.process_mercadolivre_notification({}, "shipments", "/shipments/555", "77")
    )

    assert execution_threads
    assert execution_threads[0] != event_loop_thread


def test_order_webhook_reaches_sync_with_runtime_clock(db, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.models import MarketplaceAccount

    db.add(
        MarketplaceAccount(
            provider="mercadolivre", seller_id="77", active=True, encrypted_access_token="mock"
        )
    )
    db.commit()
    synced = []
    monkeypatch.setattr(worker_settings, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(
        worker_settings.MercadoLivreClient, "get", lambda self, resource: {"id": "123"}
    )
    monkeypatch.setattr(
        worker_settings,
        "sync_order",
        lambda db, seller, resource: (
            synced.append((seller, resource))
            or SimpleNamespace(invoice_id=None, sync_status="synced")
        ),
    )
    worker_settings._process_mercadolivre_notification("orders_v2", "/orders/123", "77")
    assert synced == [("77", "/orders/123")]
