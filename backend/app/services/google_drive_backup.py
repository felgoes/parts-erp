"""Google Drive backup and OAuth helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import ErpSettings
from app.services.backup_health import cleanup_local_backups, describe_drive_error, local_backup_dir
from app.services.backup_notifications import (
    enqueue_backup_failure_notification,
    enqueue_backup_notification,
)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


class DriveAccessError(RuntimeError):
    """Autorização obtida, mas o acesso ao Drive não funcionou."""


def callback_url() -> str:
    base = str(get_settings().frontend_url).rstrip("/")
    return f"{base}/api/v1/settings/backup/google-drive/callback"


def authorization_url(settings_row: ErpSettings) -> str:
    state = encrypt_secret(
        json.dumps(
            {
                "kind": "google-drive",
                "expires": (datetime.now(UTC) + timedelta(minutes=10)).timestamp(),
            }
        )
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings_row.drive_client_id,
            "redirect_uri": callback_url(),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": DRIVE_SCOPE,
            "state": state,
        }
    )


def exchange_code(settings_row: ErpSettings, code: str) -> None:
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings_row.drive_client_id,
            "client_secret": decrypt_secret(settings_row.encrypted_drive_client_secret or ""),
            "redirect_uri": callback_url(),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        raise ValueError("Google não retornou refresh token; autorize novamente com consentimento")
    settings_row.encrypted_drive_refresh_token = encrypt_secret(str(refresh_token))
    # A conexão é validada no momento em que é configurada: sem isso o ERP marcaria o
    # backup como pronto e a primeira falha só apareceria no dia seguinte.
    validate_drive_access(settings_row)
    settings_row.backup_last_status = "ready"
    settings_row.backup_last_error = None
    settings_row.backup_last_error_code = None


def _access_token(settings_row: ErpSettings) -> str:
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings_row.drive_client_id,
            "client_secret": decrypt_secret(settings_row.encrypted_drive_client_secret or ""),
            "refresh_token": decrypt_secret(settings_row.encrypted_drive_refresh_token or ""),
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def validate_drive_access(settings_row: ErpSettings) -> None:
    """Confirma que a autorização recém-obtida realmente alcança o Drive."""
    try:
        token = _access_token(settings_row)
        response = httpx.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"pageSize": "1", "fields": "files(id)"},
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _, message = describe_drive_error(exc)
        raise DriveAccessError(message) from exc


def _cleanup_old_backups(token: str, settings_row: ErpSettings) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=settings_row.backup_retention_days)
    params = {
        "q": "name contains 'parts-erp-backup-' and trashed = false",
        "fields": "files(id,name,createdTime)",
        "pageSize": "100",
    }
    if settings_row.drive_folder_id:
        params["q"] += f" and '{settings_row.drive_folder_id}' in parents"
    response = httpx.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    for item in response.json().get("files", []):
        created = datetime.fromisoformat(str(item.get("createdTime", "")).replace("Z", "+00:00"))
        if created < cutoff:
            httpx.delete(
                f"https://www.googleapis.com/drive/v3/files/{item['id']}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            ).raise_for_status()


def _sqlite_snapshot(destination: Path) -> Path:
    """Grava a cópia local do banco no caminho definitivo (a cópia fica, dê o Drive o que der)."""
    database_url = get_settings().database_url
    if not database_url.startswith("sqlite"):
        raise RuntimeError("O backup automático do Drive atualmente requer banco SQLite")
    raw_path = database_url.split("///", 1)[-1].split("?", 1)[0]
    source_path = Path(raw_path).expanduser()
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    destination.chmod(0o600)
    return destination


def _upload_snapshot(token: str, settings_row: ErpSettings, snapshot: Path, filename: str) -> None:
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


def run_backup(db: Session) -> str:
    settings_row = db.scalar(select(ErpSettings).where(ErpSettings.id == "global"))
    if not settings_row or not settings_row.encrypted_drive_refresh_token:
        raise RuntimeError("Google Drive ainda não está conectado")
    now = datetime.now(UTC)
    filename = f"parts-erp-backup-{now.strftime('%Y%m%d-%H%M%S')}.db"
    snapshot = local_backup_dir(settings_row) / filename
    settings_row.backup_last_attempt_at = now
    try:
        # A cópia local é gravada antes de falar com o Google: se a autorização estiver
        # vencida ou o Drive inacessível, o dia continua tendo cópia no servidor.
        _sqlite_snapshot(snapshot)
        token = _access_token(settings_row)
        _upload_snapshot(token, settings_row, snapshot, filename)
        _cleanup_old_backups(token, settings_row)
        cleanup_local_backups(settings_row)
        settings_row.backup_last_at = now
        settings_row.backup_last_success_at = now
        settings_row.backup_last_status = "success"
        settings_row.backup_last_error = None
        settings_row.backup_last_error_code = None
        db.commit()
        enqueue_backup_notification(db, filename)
        return filename
    except Exception as exc:
        code, message = describe_drive_error(exc)
        settings_row.backup_last_at = now
        settings_row.backup_last_status = "failed"
        settings_row.backup_last_error = message[:1000]
        settings_row.backup_last_error_code = code[:60]
        db.commit()
        enqueue_backup_failure_notification(db, message)
        raise RuntimeError(message) from exc
