"""add purchase item unit"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "52_purchase_item_unit"
down_revision: str | None = "51_product_stock_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_items",
        sa.Column("unit", sa.String(length=24), server_default="un", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("purchase_items", "unit")
