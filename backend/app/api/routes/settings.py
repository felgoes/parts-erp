import base64
import binascii
import io
import re

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import ErpSettings, User
from app.schemas.common import ErpSettingsOut, ErpSettingsUpdate

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
        backup_retention_days=30,
        backup_destination="google_drive",
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
    return ErpSettingsOut.model_validate(current, from_attributes=True)


@router.put("", response_model=ErpSettingsOut)
def update_settings(
    payload: ErpSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ErpSettingsOut:
    values = payload.model_dump()
    values["logo_data_url"] = _validated_logo(values["logo_data_url"])
    current = db.get(ErpSettings, "global")
    if current is None:
        current = _default_settings()
        db.add(current)
    for key, value in values.items():
        setattr(current, key, value)
    db.commit()
    db.refresh(current)
    return ErpSettingsOut.model_validate(current, from_attributes=True)
