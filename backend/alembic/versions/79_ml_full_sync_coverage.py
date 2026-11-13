from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "79_ml_full_sync_coverage"
down_revision: str | None = "78_ml_full_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ml_full_inventories",
        sa.Column("operations_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ml_full_inventories",
        sa.Column("operations_coverage_start", sa.Date(), nullable=True),
    )
    op.add_column(
        "ml_full_inventories",
        sa.Column("operations_coverage_end", sa.Date(), nullable=True),
    )
    op.add_column(
        "ml_full_inventories",
        sa.Column(
            "operations_sync_status",
            sa.String(24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "ml_full_inventories",
        sa.Column("operations_sync_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ml_full_inventories", "operations_sync_error")
    op.drop_column("ml_full_inventories", "operations_sync_status")
    op.drop_column("ml_full_inventories", "operations_coverage_end")
    op.drop_column("ml_full_inventories", "operations_coverage_start")
    op.drop_column("ml_full_inventories", "operations_synced_at")
