"""add configurable backup time"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "46_backup_time"
down_revision: str | None = "45_google_drive_backup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "erp_settings",
        sa.Column("backup_time", sa.String(length=5), nullable=False, server_default="02:00"),
    )


def downgrade() -> None:
    op.drop_column("erp_settings", "backup_time")
