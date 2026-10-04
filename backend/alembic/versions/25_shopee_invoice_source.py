"""add shopee invoice source enum value

Revision ID: 25_shopee_source
Revises: 24_marketplace_auto
"""

from collections.abc import Sequence

from alembic import op

revision: str = "25_shopee_source"
down_revision: str | None = "24_marketplace_auto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE invoicesource ADD VALUE IF NOT EXISTS 'shopee'")


def downgrade() -> None:
    pass
