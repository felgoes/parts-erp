from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PushNotification
from app.services.push_notifications import deliver_pending_notifications


def enqueue_vehicle_market_update(
    db: Session,
    *,
    period: str,
    period_label: str,
) -> PushNotification | None:
    dedupe_key = f"vehicle-market-fleet:{period}"
    existing = db.scalar(
        select(PushNotification).where(PushNotification.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        category="vehicle_market",
        title="Frota do Brasil atualizada",
        body=(
            f"Os dados oficiais da frota de {period_label} já estão disponíveis "
            "em Frota do Brasil."
        )[:500],
        data={
            "type": "vehicle_market_updated",
            "period": period,
            "route": "/fleet",
            "actions": [
                {
                    "label": "Ver frota",
                    "route": "/fleet",
                    "query": {"period": period},
                }
            ],
        },
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return db.scalar(
            select(PushNotification).where(PushNotification.dedupe_key == dedupe_key)
        )
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification
