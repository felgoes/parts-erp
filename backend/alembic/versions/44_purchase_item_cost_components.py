"""store cost components on purchase items"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "44_purchase_item_cost_components"
down_revision: str | None = "43_sync_product_legacy_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("purchase_items", sa.Column("base_unit_cost", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_items", sa.Column("freight_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_items", sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_items", sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.execute("UPDATE purchase_items SET base_unit_cost = unit_cost")


def downgrade() -> None:
    op.drop_column("purchase_items", "discount_amount")
    op.drop_column("purchase_items", "tax_amount")
    op.drop_column("purchase_items", "freight_amount")
    op.drop_column("purchase_items", "base_unit_cost")
