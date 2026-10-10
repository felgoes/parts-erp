"""add purchase lifecycle, suppliers, payables and deletion audit"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "55_purchase_lifecycle_and_payables"
down_revision: str | None = "54_purchase_import_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("contact", sa.String(length=200), nullable=True),
        sa.Column("document", sa.String(length=20), nullable=True),
        sa.Column("default_delivery_days", sa.Integer(), nullable=True),
        sa.Column("default_payment_terms", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"], unique=True)

    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.add_column(sa.Column("supplier_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("supplier_order_number", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("document_date", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancel_reason", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancelled_by_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_purchase_cases_supplier_id", ["supplier_id"])
        batch_op.create_index("ix_purchase_cases_supplier_order_number", ["supplier_order_number"])
        batch_op.create_foreign_key(
            "fk_purchase_cases_supplier", "suppliers", ["supplier_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_foreign_key(
            "fk_purchase_cases_cancelled_by", "users", ["cancelled_by_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.add_column(
            sa.Column("returned_quantity", sa.Numeric(14, 3), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0")
        )

    op.create_table(
        "purchase_payables",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("purchase_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.String(length=36), nullable=True),
        sa.Column("supplier_name", sa.String(length=200), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method", sa.String(length=60), nullable=True),
        sa.Column("payment_notes", sa.String(length=255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchase_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_purchase_payables_purchase_id", "purchase_payables", ["purchase_id"])
    op.create_index("ix_purchase_payables_status", "purchase_payables", ["status"])

    op.create_table(
        "purchase_deletions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("purchase_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("purchase_type", sa.String(length=30), nullable=False),
        sa.Column("supplier_name", sa.String(length=200), nullable=True),
        sa.Column("items_summary", sa.Text(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_purchase_deletions_purchase_id", "purchase_deletions", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_deletions_purchase_id", table_name="purchase_deletions")
    op.drop_table("purchase_deletions")
    op.drop_index("ix_purchase_payables_status", table_name="purchase_payables")
    op.drop_index("ix_purchase_payables_purchase_id", table_name="purchase_payables")
    op.drop_table("purchase_payables")
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.drop_column("discount_percent")
        batch_op.drop_column("returned_quantity")
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.drop_constraint("fk_purchase_cases_cancelled_by", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_cases_supplier", type_="foreignkey")
        batch_op.drop_index("ix_purchase_cases_supplier_order_number")
        batch_op.drop_index("ix_purchase_cases_supplier_id")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("cancelled_by_id")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("cancel_reason")
        batch_op.drop_column("document_date")
        batch_op.drop_column("supplier_order_number")
        batch_op.drop_column("supplier_id")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
