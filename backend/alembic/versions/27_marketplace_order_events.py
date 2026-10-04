"""store marketplace order status history

Revision ID: 27_marketplace_events
Revises: 26_repair_ml_config
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "27_marketplace_events"
down_revision: str | None = "26_repair_ml_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketplace_order_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["marketplace_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_order_events_order_created", "marketplace_order_events", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_order_events_order_created", table_name="marketplace_order_events")
    op.drop_table("marketplace_order_events")
