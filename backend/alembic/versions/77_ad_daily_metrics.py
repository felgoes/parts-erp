"""store daily marketplace ad visits"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "77_ad_daily_metrics"
down_revision: str | None = "76_vehicle_fleet_import_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product_marketplace_listings", sa.Column("parent_item_id", sa.String(length=80), nullable=True))
    op.create_table(
        "ad_daily_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("marketplace_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False, server_default="mercadolivre"),
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("parent_item_id", sa.String(length=80)),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("visits", sa.Integer()),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_status", sa.String(length=20), nullable=False, server_default="ok"),
    )
    op.create_index("uq_ad_daily_metrics_account_channel_item_date", "ad_daily_metrics", ["account_id", "channel", "item_id", "metric_date"], unique=True)
    op.create_index("ix_ad_daily_metrics_account_id", "ad_daily_metrics", ["account_id"])
    op.create_index("ix_ad_daily_metrics_date", "ad_daily_metrics", ["metric_date"])


def downgrade() -> None:
    op.drop_index("ix_ad_daily_metrics_date", table_name="ad_daily_metrics")
    op.drop_index("ix_ad_daily_metrics_account_id", table_name="ad_daily_metrics")
    op.drop_index("uq_ad_daily_metrics_account_channel_item_date", table_name="ad_daily_metrics")
    op.drop_table("ad_daily_metrics")
    op.drop_column("product_marketplace_listings", "parent_item_id")
