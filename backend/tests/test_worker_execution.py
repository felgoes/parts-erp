import asyncio
import threading

from app.workers import settings as worker_settings


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
