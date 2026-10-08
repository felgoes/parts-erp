from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import PushDevice, PushNotification, PushPreference, User
from app.schemas.common import PushDeviceRegistration, PushNotificationOut, PushPreferenceOut, PushPreferenceUpdate

router = APIRouter(prefix="/push", tags=["Notificações"])

CATEGORIES = {
    "sales": ("Novas vendas", "Receba um aviso quando uma venda entrar pelas plataformas."),
    "order_status": ("Status dos pedidos", "Pagamento, despacho, entrega, cancelamento e devolução."),
    "fiscal": ("Notas e etiquetas", "Emissão ou falha de nota fiscal e etiqueta de envio."),
    "backup": ("Backups", "Conclusão ou falha no backup do ERP."),
    "system": ("Sistema", "Alertas técnicos e avisos importantes do ERP."),
}


@router.get("/preferences", response_model=list[PushPreferenceOut])
def list_preferences(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[PushPreferenceOut]:
    saved = {p.category: p for p in db.scalars(select(PushPreference).where(PushPreference.user_id == user.id))}
    return [PushPreferenceOut(category=key, label=label, description=description, enabled=saved[key].enabled if key in saved else True, sound=saved[key].sound if key in saved else "system") for key, (label, description) in CATEGORIES.items()]


@router.put("/preferences/{category}", response_model=PushPreferenceOut)
def update_preference(category: str, payload: PushPreferenceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PushPreferenceOut:
    if category not in CATEGORIES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Categoria de notificação inválida")
    preference = db.scalar(select(PushPreference).where(PushPreference.user_id == user.id, PushPreference.category == category))
    if preference is None:
        preference = PushPreference(user_id=user.id, category=category, enabled=payload.enabled, sound=payload.sound or "system")
        db.add(preference)
    else:
        preference.enabled = payload.enabled
        if payload.sound is not None:
            preference.sound = payload.sound
    db.commit()
    return PushPreferenceOut(category=category, label=CATEGORIES[category][0], description=CATEGORIES[category][1], enabled=preference.enabled, sound=preference.sound)


@router.get("/history", response_model=list[PushNotificationOut])
def notification_history(limit: int = 50, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[PushNotificationOut]:
    rows = list(db.scalars(select(PushNotification).order_by(PushNotification.created_at.desc()).limit(max(1, min(limit, 100)))))
    return [PushNotificationOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/devices", status_code=204)
def register_device(
    payload: PushDeviceRegistration,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Associates one FCM token with the logged-in user.

    A token can move between users after logout/login on the same phone, so it
    is deliberately reassigned instead of rejected.
    """
    device = db.scalar(select(PushDevice).where(PushDevice.token == payload.token))
    if device is None:
        device = PushDevice(user_id=user.id, token=payload.token, platform=payload.platform, sound_settings_version=payload.sound_settings_version)
        db.add(device)
    else:
        device.user_id = user.id
        device.platform = payload.platform
        device.active = True
        device.sound_settings_version = max(device.sound_settings_version, payload.sound_settings_version)
        device.last_seen_at = datetime.now(UTC)
    db.commit()


@router.delete("/devices/current", status_code=204)
def deactivate_device(
    payload: PushDeviceRegistration,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    device = db.scalar(
        select(PushDevice).where(PushDevice.token == payload.token, PushDevice.user_id == user.id)
    )
    if device is not None:
        device.active = False
        device.last_seen_at = datetime.now(UTC)
        db.commit()
