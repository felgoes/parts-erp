"""add payable payments with partial settlement and reconciliation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "56_payable_payments"
down_revision: str | None = "55_purchase_lifecycle_and_payables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_payables") as batch_op:
        batch_op.add_column(
            sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0")
        )

    op.create_table(
        "payable_payments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("payable_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("reconciled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payable_id"], ["purchase_payables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reconciled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payable_payments_payable_id", "payable_payments", ["payable_id"])
    op.create_index(
        "ix_payable_payments_idempotency_key", "payable_payments", ["idempotency_key"], unique=True
    )

    # Titles already marked as paid keep their history: backfill one full payment for each.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO payable_payments
                (id, payable_id, amount, paid_at, method, notes, reconciled, created_at)
            SELECT
                lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))), 2) || '-a' ||
                substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
                id, amount, coalesce(paid_at, updated_at), payment_method, payment_notes,
                0, coalesce(paid_at, updated_at)
            FROM purchase_payables
            WHERE status = 'paid'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE purchase_payables
            SET paid_amount = amount
            WHERE status = 'paid'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_payable_payments_idempotency_key", table_name="payable_payments")
    op.drop_index("ix_payable_payments_payable_id", table_name="payable_payments")
    op.drop_table("payable_payments")
    with op.batch_alter_table("purchase_payables") as batch_op:
        batch_op.drop_column("paid_amount")
