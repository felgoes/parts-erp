"""allow Shopee as an invoice source on PostgreSQL

Revision ID: 25_shopee_source
Revises: 24_marketplace_auto
Create Date: 2026-10-03 16:30:00
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
    # PostgreSQL não remove um valor de enum com segurança sem recriar a coluna.
    pass
