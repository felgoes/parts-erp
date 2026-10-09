import base64
import binascii
import io
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.config import get_settings
from app.core.permissions import Permission
from app.core.security import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models import ErpSettings, User
from app.schemas.common import ErpSettingsOut, ErpSettingsUpdate
from app.services.google_drive_backup import (
    authorization_url,
    callback_url,
    exchange_code,
    run_backup,
)
from app.services.purchase_import import PROFILE_SCHEMA, delete_profile, list_profiles, save_profile

router = APIRouter(prefix="/settings", tags=["Configurações"])
LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_PATTERN = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$")


def _get_settings(db: Session) -> ErpSettings:
    return db.get(ErpSettings, "global") or _default_settings()


def _default_settings() -> ErpSettings:
    return ErpSettings(
        id="global",
        company_name="Parts ERP",
        company_short_name="Parts",
        logo_data_url=None,
        backup_enabled=False,
        backup_frequency="daily",
        backup_time="02:00",
        backup_retention_days=30,
        backup_destination="google_drive",
        backup_last_status="setup_required",
    )


def _validated_logo(value: str | None) -> str | None:
    if value is None:
        return None
    match = LOGO_PATTERN.fullmatch(value)
    if not match:
        raise HTTPException(status_code=422, detail="Envie um logo PNG, JPEG ou WebP válido")
    mime, encoded = match.groups()
    try:
        contents = base64.b64decode(encoded, validate=True)
        if not contents or len(contents) > LOGO_MAX_BYTES:
            raise ValueError("Tamanho inválido")
        with Image.open(io.BytesIO(contents)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Formato inválido")
            image.verify()
    except (binascii.Error, OSError, ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(
            status_code=422, detail="O arquivo de logo não é uma imagem válida"
        ) from exc
    return f"data:image/{mime};base64,{encoded}"


@router.get("", response_model=ErpSettingsOut)
def read_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ErpSettingsOut:
    current = _get_settings(db)
    return _settings_out(current)


def _settings_out(current: ErpSettings) -> ErpSettingsOut:
    return ErpSettingsOut(
        company_name=current.company_name,
        company_short_name=current.company_short_name,
        logo_data_url=current.logo_data_url,
        backup_enabled=current.backup_enabled,
        backup_frequency=current.backup_frequency,
        backup_time=current.backup_time,
        backup_retention_days=current.backup_retention_days,
        backup_destination=current.backup_destination,
        backup_ready=bool(current.encrypted_drive_refresh_token),
        backup_status="ready" if current.encrypted_drive_refresh_token else "setup_required",
        drive_client_id=current.drive_client_id,
        drive_client_secret_configured=bool(current.encrypted_drive_client_secret),
        drive_folder_id=current.drive_folder_id,
        drive_connected=bool(current.encrypted_drive_refresh_token),
        backup_last_at=current.backup_last_at,
        backup_last_status=current.backup_last_status,
        backup_last_error=current.backup_last_error,
    )


@router.put("", response_model=ErpSettingsOut)
def update_settings(
    payload: ErpSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ErpSettingsOut:
    values = payload.model_dump(exclude={"drive_client_secret"})
    drive_secret = payload.drive_client_secret.strip() if payload.drive_client_secret else ""
    values["logo_data_url"] = _validated_logo(values["logo_data_url"])
    current = db.get(ErpSettings, "global")
    if current is None:
        current = _default_settings()
        db.add(current)
    for key, value in values.items():
        setattr(current, key, value)
    if drive_secret:
        current.encrypted_drive_client_secret = encrypt_secret(drive_secret)
    if current.drive_client_id and current.encrypted_drive_client_secret:
        current.backup_last_status = "setup_required"
    db.commit()
    db.refresh(current)
    return _settings_out(current)


@router.get("/backup/google-drive/connect")
def connect_google_drive(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict[str, str]:
    current = db.get(ErpSettings, "global")
    if not current or not current.drive_client_id or not current.encrypted_drive_client_secret:
        raise HTTPException(
            status_code=400, detail="Informe o Client ID e o segredo OAuth do Google Drive primeiro"
        )
    return {"authorization_url": authorization_url(current), "redirect_uri": callback_url()}


@router.get("/backup/google-drive/callback")
def google_drive_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    destination = f"{str(get_settings().frontend_url).rstrip('/')}/settings"
    if error or not code or not state:
        return RedirectResponse(f"{destination}?drive_error=cancelled")
    try:
        decrypt_secret(state)
        current = db.get(ErpSettings, "global")
        if not current:
            raise ValueError("configuração ausente")
        exchange_code(current, code)
        db.commit()
        return RedirectResponse(f"{destination}?drive_connected=true")
    except Exception:
        db.rollback()
        return RedirectResponse(f"{destination}?drive_error=oauth")


@router.post("/backup/run")
def run_google_drive_backup(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict[str, str]:
    try:
        filename = run_backup(db)
        return {"filename": filename, "message": "Backup concluído e enviado ao Google Drive."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/purchase-import-profiles")
def purchase_import_profiles(
    _: User = Depends(get_current_user),
) -> dict[str, object]:
    return {"schema": PROFILE_SCHEMA, "profiles": list_profiles()}


@router.post("/purchase-import-profiles")
def upload_purchase_import_profile(
    file: UploadFile = File(...),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict[str, object]:
    if Path(file.filename or "").suffix.lower() != ".json":
        raise HTTPException(status_code=415, detail="Envie um perfil no formato JSON.")
    raw = file.file.read(100_001)
    if len(raw) > 100_000:
        raise HTTPException(status_code=413, detail="O perfil deve ter até 100 KB.")
    try:
        payload = json.loads(raw)
        profile = save_profile(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Perfil inválido: {exc}") from exc
    return {"profile_id": profile["profile_id"], "name": profile["name"], "status": "saved"}


@router.delete("/purchase-import-profiles/{profile_id}")
def remove_purchase_import_profile(
    profile_id: str,
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict[str, str]:
    if profile_id in {"aliexpress", "mercado_livre", "shopee", "amazon", "alibaba"}:
        raise HTTPException(status_code=409, detail="Perfis nativos não podem ser removidos.")
    if not delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Perfil personalizado não encontrado.")
    return {"status": "deleted"}
