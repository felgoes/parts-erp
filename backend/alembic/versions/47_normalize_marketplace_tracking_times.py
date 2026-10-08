"""normalize Mercado Livre order and tracking times to UTC"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "47_normalize_ml_tracking_times"
down_revision: str | None = "46_backup_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def _parse_platform_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def upgrade() -> None:
    bind = op.get_bind()
    orders = sa.table(
        "marketplace_orders",
        sa.column("id", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("payload", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    events = sa.table(
        "marketplace_order_events",
        sa.column("id", sa.String()),
        sa.column("event_type", sa.String()),
        sa.column("payload", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    invoices = sa.table(
        "sales_invoices",
        sa.column("id", sa.String()),
        sa.column("marketplace_order_id", sa.String()),
        sa.column("issued_at", sa.DateTime(timezone=True)),
    )

    rows = bind.execute(
        sa.select(orders.c.id, orders.c.payload).where(orders.c.provider == "mercadolivre")
    )
    for order_id, payload in rows:
        if not isinstance(payload, dict):
            continue
        order_created_at = _parse_platform_datetime(
            payload.get("date_created") or payload.get("_erp_source_created_at")
        )
        if order_created_at:
            bind.execute(
                sa.update(orders)
                .where(orders.c.id == order_id)
                .values(created_at=order_created_at)
            )
            bind.execute(
                sa.update(invoices)
                .where(invoices.c.marketplace_order_id == str(payload.get("id") or ""))
                .values(issued_at=order_created_at)
            )

    event_rows = bind.execute(
        sa.select(events.c.id, events.c.payload).where(
            events.c.event_type.in_(("shipment_status", "order_status", "after_sale"))
        )
    )
    for event_id, payload in event_rows:
        if not isinstance(payload, dict):
            continue
        event_at = _parse_platform_datetime(
            payload.get("source_date")
            or payload.get("source_updated_at")
            or payload.get("date_created")
            or payload.get("created_at")
            or payload.get("updated_at")
        )
        if event_at:
            bind.execute(
                sa.update(events).where(events.c.id == event_id).values(created_at=event_at)
            )


def downgrade() -> None:
    # The previous values were timezone-corrupted wall-clock timestamps. Keeping
    # the normalized instants is safer than restoring inaccurate display times.
    pass
