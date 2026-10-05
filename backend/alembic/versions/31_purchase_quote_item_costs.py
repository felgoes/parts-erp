"""store per-item supplier prices in purchase quotes"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "31_purchase_quote_costs"
down_revision: str | None = "30_purchase_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_quotes",
        sa.Column("item_costs", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("purchase_quotes", "item_costs")
