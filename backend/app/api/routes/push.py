from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import PushDevice, User
from app.schemas.common import PushDeviceRegistration

router = APIRouter(prefix="/push", tags=["Notificações"])


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
        device = PushDevice(user_id=user.id, token=payload.token, platform=payload.platform)
        db.add(device)
    else:
        device.user_id = user.id
        device.platform = payload.platform
        device.active = True
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
