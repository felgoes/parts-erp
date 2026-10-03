"""marketplace configuration

Revision ID: 21a1_marketplace_config
Revises: 0afb91b11bb1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21a1_marketplace_config"
down_revision: str | None = "0afb91b11bb1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketplace_config",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=False),
        sa.Column("encrypted_client_secret", sa.Text(), nullable=True),
        sa.Column("redirect_uri", sa.String(length=500), nullable=True),
        sa.Column("site_id", sa.String(length=20), nullable=False),
        sa.Column("import_orders", sa.Boolean(), nullable=False),
        sa.Column("automatic_stock", sa.Boolean(), nullable=False),
        sa.Column("sync_documents", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("marketplace_config")
