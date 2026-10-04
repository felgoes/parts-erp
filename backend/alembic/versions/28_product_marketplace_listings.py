"""store marketplace listing metadata and metrics"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "28_product_listings"
down_revision: str | None = "27_marketplace_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_marketplace_listings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_item_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("permalink", sa.String(length=1000), nullable=True),
        sa.Column("thumbnail", sa.String(length=1000), nullable=True),
        sa.Column("images", sa.JSON(), nullable=False),
        sa.Column("marketplace_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("available_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("sold_quantity", sa.Integer(), nullable=True),
        sa.Column("visits", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("synchronized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_item_id", name="uq_product_marketplace_listing"),
    )
    op.create_index("ix_product_marketplace_listing_product", "product_marketplace_listings", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_marketplace_listing_product", table_name="product_marketplace_listings")
    op.drop_table("product_marketplace_listings")
