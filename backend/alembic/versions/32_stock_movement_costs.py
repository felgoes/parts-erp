"""capture cost snapshots for stock movements"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "32_stock_movement_costs"
down_revision: str | None = "31_purchase_quote_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stock_movements", sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True))
    op.add_column("stock_movements", sa.Column("movement_value", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_movements", "movement_value")
    op.drop_column("stock_movements", "unit_cost")
