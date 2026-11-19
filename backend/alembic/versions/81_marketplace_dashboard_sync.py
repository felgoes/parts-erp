from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "81_marketplace_dashboard_sync"
down_revision: str | None = "80_ml_full_unknown_declared_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketplace_dashboard_syncs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["marketplace_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marketplace_dashboard_syncs_account_id",
        "marketplace_dashboard_syncs",
        ["account_id"],
    )
    op.create_index(
        "uq_marketplace_dashboard_sync_period",
        "marketplace_dashboard_syncs",
        ["account_id", "period_start", "period_end"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_marketplace_dashboard_sync_period", table_name="marketplace_dashboard_syncs")
    op.drop_index("ix_marketplace_dashboard_syncs_account_id", table_name="marketplace_dashboard_syncs")
    op.drop_table("marketplace_dashboard_syncs")
