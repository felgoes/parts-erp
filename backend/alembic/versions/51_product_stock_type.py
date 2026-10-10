"""separate warehouse inventory from sale products"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "51_product_stock_type"
down_revision: str | None = "50_persistent_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("stock_type", sa.String(length=20), server_default="product", nullable=False),
    )
    op.create_index("ix_products_stock_type", "products", ["stock_type"])


def downgrade() -> None:
    op.drop_index("ix_products_stock_type", table_name="products")
    op.drop_column("products", "stock_type")
