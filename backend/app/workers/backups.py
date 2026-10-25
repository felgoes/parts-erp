import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ErpSettings
from app.services.backup_health import current_window_day, scheduled_backup_due
from app.services.google_drive_backup import run_backup

logger = logging.getLogger(__name__)


def _scheduled_backup_is_due(settings: ErpSettings, now_utc: datetime | None = None) -> bool:
    """Return whether the worker should attempt the backup now."""
    return scheduled_backup_due(settings, now_utc)


def _record_backup_attempt(settings: ErpSettings, now_utc: datetime | None = None) -> None:
    """Conta a tentativa na janela do dia: é o que limita a insistência."""
    window = current_window_day(settings, now_utc)
    if window is None:
        return
    if settings.backup_attempts_date != window.isoformat():
        settings.backup_attempts_date = window.isoformat()
        settings.backup_attempts_today = 0
    settings.backup_attempts_today = int(settings.backup_attempts_today or 0) + 1


def run_scheduled_backup() -> str | None:
    with SessionLocal() as db:
        settings = db.scalar(select(ErpSettings).where(ErpSettings.id == "global"))
        if (
            not settings
            or not settings.backup_enabled
            or not settings.encrypted_drive_refresh_token
        ):
            return None
        if not _scheduled_backup_is_due(settings):
            return None
        _record_backup_attempt(settings)
        db.commit()
        try:
            return run_backup(db)
        except Exception:
            logger.exception("scheduled Google Drive backup failed")
            return None


async def scheduled_google_drive_backup(ctx: dict[str, Any]) -> str | None:
    del ctx
    return await asyncio.to_thread(run_scheduled_backup)
