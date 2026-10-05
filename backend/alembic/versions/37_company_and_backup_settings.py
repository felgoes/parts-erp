"""add shared company identity and backup policy settings"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "37_company_backup_settings"
down_revision: str | None = "36_user_access_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "erp_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_name", sa.String(120), nullable=False, server_default="Parts ERP"),
        sa.Column("company_short_name", sa.String(40), nullable=False, server_default="Parts"),
        sa.Column("logo_data_url", sa.Text()),
        sa.Column("backup_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backup_frequency", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("backup_retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("backup_destination", sa.String(30), nullable=False, server_default="google_drive"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("erp_settings")
