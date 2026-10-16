"""Avisos de backup: o sucesso informa e a falha cobra ação de quem administra.

Separado de `push_notifications.py` (que ficou com a entrega e as demais categorias) para os
dois arquivos caberem no teto de leitura do projeto.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PushNotification
from app.services.backup_health import local_day
from app.services.push_notifications import deliver_pending_notifications

FAILURE_CATEGORY = "backup"
MANAGER_AUDIENCE = "managers"


def enqueue_backup_notification(db: Session, filename: str) -> PushNotification | None:
    """Avisa que o backup foi concluído e enviado ao Google Drive."""
    dedupe_key = f"backup:{filename}"
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        category=FAILURE_CATEGORY,
        title="Backup concluído",
        body=f"Cópia do Parts ERP guardada no servidor e enviada ao Google Drive: {filename}"[:500],
        data={"type": "backup_completed", "filename": filename, "route": "/settings"},
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


def enqueue_backup_failure_notification(db: Session, reason: str) -> PushNotification | None:
    """Avisa administrador e gerente uma vez por dia enquanto o backup não voltar.

    A falha de backup era silenciosa; o aviso ativo é o que impede a proteção de sumir sem
    ninguém notar. A chave de deduplicação usa o dia local, então as tentativas seguintes do
    mesmo dia não repetem a notificação.
    """
    dedupe_key = f"backup-failed:{local_day(datetime.now(UTC)).isoformat()}"
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        category=FAILURE_CATEGORY,
        title="Backup do ERP não foi concluído",
        body=reason[:500],
        data={"type": "backup_failed", "route": "/settings", "audience": MANAGER_AUDIENCE},
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification
