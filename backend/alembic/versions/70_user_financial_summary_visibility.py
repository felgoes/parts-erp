"""store per-user dashboard financial summary visibility"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "70_user_financial_summary_visibility"
down_revision: str | None = "69_backfill_product_marketplace_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "financial_summary_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "financial_summary_hidden")
