"""restore Mercado Livre invoice dates from original order timestamps

Revision ID: 29_ml_invoice_dates
Revises: 28_product_listings
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "29_ml_invoice_dates"
down_revision: str | None = "28_product_listings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    orders = sa.table(
        "marketplace_orders",
        sa.column("invoice_id", sa.String()),
        sa.column("payload", sa.JSON()),
    )
    invoices = sa.table(
        "sales_invoices",
        sa.column("id", sa.String()),
        sa.column("issued_at", sa.DateTime(timezone=True)),
    )
    rows = bind.execute(
        sa.select(orders.c.invoice_id, orders.c.payload).where(orders.c.invoice_id.is_not(None))
    )
    for invoice_id, payload in rows:
        if not isinstance(payload, dict):
            continue
        raw_date = payload.get("date_created")
        if not isinstance(raw_date, str) or not raw_date.strip():
            continue
        try:
            order_date = datetime.fromisoformat(raw_date.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        order_date = (
            order_date.replace(tzinfo=UTC)
            if order_date.tzinfo is None
            else order_date.astimezone(UTC)
        )
        bind.execute(
            sa.update(invoices).where(invoices.c.id == invoice_id).values(issued_at=order_date)
        )


def downgrade() -> None:
    # The pre-correction webhook timestamp was not retained separately.
    # Reverting would require inventing an inaccurate invoice date.
    pass
