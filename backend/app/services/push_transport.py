"""Firebase transport for persisted push notifications."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import get_settings
from app.models import PushDevice, PushNotification

logger = logging.getLogger(__name__)
SOUND_CATEGORIES = {"sales", "order_status", "fiscal", "backup", "system"}
SOUND_OPTIONS = {"system", "bell", "chime", "soft", "kaching", "silent"}
_access_token = ""
_access_token_expires_at = 0.0


def _firebase_credentials() -> dict[str, Any] | None:
    credential_file = get_settings().firebase_service_account_file.strip()
    if not credential_file:
        return None
    path = Path(credential_file).expanduser()
    if not path.is_file():
        logger.warning("Firebase credential file is unavailable")
        return None
    try:
        credentials = json.loads(path.read_text(encoding="utf-8"))
        if not all(
            credentials.get(field) for field in ("client_email", "private_key", "project_id")
        ):
            raise ValueError("service account incompleta")
        return credentials
    except Exception:  # noqa: BLE001
        logger.exception("Could not load Firebase push credential")
        return None


def _firebase_access_token(credentials: dict[str, Any]) -> str:
    global _access_token, _access_token_expires_at
    if _access_token and _access_token_expires_at > time.time() + 60:
        return _access_token
    issued_at = int(time.time())
    assertion = jwt.encode(
        {
            "iss": credentials["client_email"],
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        credentials["private_key"],
        algorithm="RS256",
    )
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    _access_token = str(payload["access_token"])
    _access_token_expires_at = time.time() + int(payload.get("expires_in", 3600))
    return _access_token


def deliver(
    credentials: dict[str, Any],
    devices: list[PushDevice],
    notification: PushNotification,
    sound_by_user: dict[str, str] | None = None,
) -> None:
    access_token = _firebase_access_token(credentials)
    url = f"https://fcm.googleapis.com/v1/projects/{credentials['project_id']}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}"}
    delivered, failures = 0, []
    for device in devices:
        sound = (sound_by_user or {}).get(device.user_id, "system")
        if sound not in SOUND_OPTIONS or (sound == "kaching" and device.sound_settings_version < 2):
            sound = "system"
        channel_id = "sales"
        if (
            device.sound_settings_version >= 1
            and notification.category in SOUND_CATEGORIES
            and sound != "system"
        ):
            channel_id = f"parts_v1_{notification.category}_{sound}"
        data = {str(key): str(value) for key, value in notification.data.items()}
        if channel_id != "sales":
            data.update(notification_channel=channel_id, notification_sound=sound)
        response = httpx.post(
            url,
            headers=headers,
            json={
                "message": {
                    "token": device.token,
                    "notification": {"title": notification.title, "body": notification.body},
                    "data": data,
                    "android": {"priority": "HIGH", "notification": {"channel_id": channel_id}},
                }
            },
            timeout=15,
        )
        if response.is_success:
            delivered += 1
            continue
        detail = response.text[:1000]
        failures.append(detail)
        if response.status_code == 404 or "UNREGISTERED" in detail or "INVALID_ARGUMENT" in detail:
            device.active = False
    if not delivered:
        raise RuntimeError("; ".join(failures) or "Firebase recusou a entrega")
