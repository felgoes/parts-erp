"""Google Drive backup and OAuth helpers."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import ErpSettings
from app.services.push_notifications import enqueue_backup_notification

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def callback_url() -> str:
    return f"{str(get_settings().frontend_url).rstrip('/')}/api/v1/settings/backup/google-drive/callback"


def authorization_url(settings_row: ErpSettings) -> str:
    state = encrypt_secret(json.dumps({"kind": "google-drive", "expires": (datetime.now(UTC) + timedelta(minutes=10)).timestamp()}))
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings_row.drive_client_id,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": DRIVE_SCOPE,
        "state": state,
    })


def exchange_code(settings_row: ErpSettings, code: str) -> None:
    response = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": settings_row.drive_client_id,
        "client_secret": decrypt_secret(settings_row.encrypted_drive_client_secret or ""),
        "redirect_uri": callback_url(),
        "grant_type": "authorization_code",
    }, timeout=20)
    response.raise_for_status()
    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        raise ValueError("Google não retornou refresh token; autorize novamente com consentimento")
    settings_row.encrypted_drive_refresh_token = encrypt_secret(str(refresh_token))
    settings_row.backup_last_status = "ready"
    settings_row.backup_last_error = None


def _access_token(settings_row: ErpSettings) -> str:
    response = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": settings_row.drive_client_id,
        "client_secret": decrypt_secret(settings_row.encrypted_drive_client_secret or ""),
        "refresh_token": decrypt_secret(settings_row.encrypted_drive_refresh_token or ""),
        "grant_type": "refresh_token",
    }, timeout=20)
    response.raise_for_status()
    return str(response.json()["access_token"])


def _cleanup_old_backups(token: str, settings_row: ErpSettings) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=settings_row.backup_retention_days)
    params = {"q": "name contains 'parts-erp-backup-' and trashed = false", "fields": "files(id,name,createdTime)", "pageSize": "100"}
    if settings_row.drive_folder_id:
        params["q"] += f" and '{settings_row.drive_folder_id}' in parents"
    response = httpx.get("https://www.googleapis.com/drive/v3/files", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    response.raise_for_status()
    for item in response.json().get("files", []):
        created = datetime.fromisoformat(str(item.get("createdTime", "")).replace("Z", "+00:00"))
        if created < cutoff:
            httpx.delete(f"https://www.googleapis.com/drive/v3/files/{item['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=30).raise_for_status()


def _sqlite_snapshot() -> Path:
    database_url = get_settings().database_url
    if not database_url.startswith("sqlite"):
        raise RuntimeError("O backup automático do Drive atualmente requer banco SQLite")
    raw_path = database_url.split("///", 1)[-1].split("?", 1)[0]
    source_path = Path(raw_path).expanduser()
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    fd, temporary = tempfile.mkstemp(prefix="parts-erp-backup-", suffix=".db")
    Path(temporary).unlink(missing_ok=True)
    with sqlite3.connect(source_path) as source, sqlite3.connect(temporary) as target:
        source.backup(target)
    return Path(temporary)


def run_backup(db: Session) -> str:
    settings_row = db.scalar(select(ErpSettings).where(ErpSettings.id == "global"))
    if not settings_row or not settings_row.encrypted_drive_refresh_token:
        raise RuntimeError("Google Drive ainda não está conectado")
    snapshot = _sqlite_snapshot()
    filename = f"parts-erp-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db"
    try:
        token = _access_token(settings_row)
        metadata: dict[str, object] = {"name": filename, "mimeType": "application/x-sqlite3"}
        if settings_row.drive_folder_id:
            metadata["parents"] = [settings_row.drive_folder_id]
        response = httpx.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": (None, json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (filename, snapshot.read_bytes(), "application/x-sqlite3"),
            },
            timeout=120,
        )
        response.raise_for_status()
        _cleanup_old_backups(token, settings_row)
        settings_row.backup_last_at = datetime.now(UTC)
        settings_row.backup_last_status = "success"
        settings_row.backup_last_error = None
        db.commit()
        enqueue_backup_notification(db, filename)
        return filename
    except Exception as exc:
        settings_row.backup_last_status = "failed"
        settings_row.backup_last_error = str(exc)[:1000]
        db.commit()
        raise
    finally:
        snapshot.unlink(missing_ok=True)
