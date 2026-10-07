"""support company expenses and purchase attachments"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "41_purchase_expenses_and_attachments"
down_revision: str | None = "40_push_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("purchase_cases", sa.Column("purchase_type", sa.String(length=30), nullable=False, server_default="parts"))
    op.add_column("purchase_cases", sa.Column("expense_category", sa.String(length=80), nullable=True))
    op.add_column("purchase_cases", sa.Column("expense_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("purchase_cases", sa.Column("supplier_name", sa.String(length=200), nullable=True))
    op.create_index("ix_purchase_cases_purchase_type", "purchase_cases", ["purchase_type"])
    op.create_table(
        "purchase_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("purchase_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchase_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_attachments_purchase_id", "purchase_attachments", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_attachments_purchase_id", table_name="purchase_attachments")
    op.drop_table("purchase_attachments")
    op.drop_index("ix_purchase_cases_purchase_type", table_name="purchase_cases")
    op.drop_column("purchase_cases", "supplier_name")
    op.drop_column("purchase_cases", "expense_amount")
    op.drop_column("purchase_cases", "expense_category")
    op.drop_column("purchase_cases", "purchase_type")
