"""add Shopee integration configuration
Revision ID: 22a_shopee_config
Revises: 21a1_marketplace_config
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
revision: str = "22a_shopee_config"
down_revision: str | None = "21a1_marketplace_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
def upgrade() -> None:
    op.create_table(
        "shopee_config",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=120), nullable=False),
        sa.Column("encrypted_partner_key", sa.Text(), nullable=True),
        sa.Column("shop_id", sa.String(length=80), nullable=True),
        sa.Column("redirect_uri", sa.String(length=500), nullable=True),
        sa.Column("region", sa.String(length=10), nullable=False),
        sa.Column("import_orders", sa.Boolean(), nullable=False),
        sa.Column("automatic_stock", sa.Boolean(), nullable=False),
        sa.Column("sync_documents", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
def downgrade() -> None:
    op.drop_table("shopee_config")
