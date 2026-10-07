"""store freight, taxes, discounts and cost allocation for quotes"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "42_quote_cost_breakdown"
down_revision: str | None = "41_purchase_expenses_and_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("purchase_quotes", sa.Column("freight_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_quotes", sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_quotes", sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("purchase_quotes", sa.Column("allocation_method", sa.String(length=30), nullable=False, server_default="proportional"))


def downgrade() -> None:
    op.drop_column("purchase_quotes", "allocation_method")
    op.drop_column("purchase_quotes", "discount_amount")
    op.drop_column("purchase_quotes", "tax_amount")
    op.drop_column("purchase_quotes", "freight_amount")
