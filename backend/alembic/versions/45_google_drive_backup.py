"""store Google Drive OAuth settings and backup state"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "45_google_drive_backup"
down_revision: str | None = "44_purchase_item_cost_components"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("erp_settings", sa.Column("drive_client_id", sa.String(length=255), nullable=True))
    op.add_column("erp_settings", sa.Column("encrypted_drive_client_secret", sa.Text(), nullable=True))
    op.add_column("erp_settings", sa.Column("encrypted_drive_refresh_token", sa.Text(), nullable=True))
    op.add_column("erp_settings", sa.Column("drive_folder_id", sa.String(length=255), nullable=True))
    op.add_column("erp_settings", sa.Column("backup_last_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("erp_settings", sa.Column("backup_last_status", sa.String(length=30), nullable=False, server_default="setup_required"))
    op.add_column("erp_settings", sa.Column("backup_last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("erp_settings", "backup_last_error")
    op.drop_column("erp_settings", "backup_last_status")
    op.drop_column("erp_settings", "backup_last_at")
    op.drop_column("erp_settings", "drive_folder_id")
    op.drop_column("erp_settings", "encrypted_drive_refresh_token")
    op.drop_column("erp_settings", "encrypted_drive_client_secret")
    op.drop_column("erp_settings", "drive_client_id")
