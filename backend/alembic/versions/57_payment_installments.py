"""add payment conditions and payable installments"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "57_payment_installments"
down_revision: str | None = "56_payable_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_quotes") as batch_op:
        batch_op.add_column(
            sa.Column("payment_type", sa.String(length=20), nullable=False, server_default="cash")
        )
        batch_op.add_column(
            sa.Column("installment_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("first_due_days", sa.Integer(), nullable=False, server_default="30")
        )
        batch_op.add_column(
            sa.Column("interval_days", sa.Integer(), nullable=False, server_default="30")
        )

    with op.batch_alter_table("purchase_payables") as batch_op:
        batch_op.add_column(
            sa.Column("payment_type", sa.String(length=20), nullable=False, server_default="cash")
        )
        batch_op.add_column(
            sa.Column("installment_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("first_due_days", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("interval_days", sa.Integer(), nullable=False, server_default="30")
        )
        batch_op.add_column(sa.Column("payment_terms", sa.String(length=120), nullable=True))

    op.create_table(
        "payable_installments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("payable_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payable_id"], ["purchase_payables.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payable_installments_payable_id", "payable_installments", ["payable_id"])
    op.create_index(
        "ix_payable_installments_payable_number",
        "payable_installments",
        ["payable_id", "number"],
    )

    with op.batch_alter_table("payable_payments") as batch_op:
        batch_op.add_column(sa.Column("installment_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_payable_payments_installment_id", ["installment_id"])
        batch_op.create_foreign_key(
            "fk_payable_payments_installment",
            "payable_installments",
            ["installment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Títulos já existentes ganham a parcela única no vencimento que já tinham, e os
    # pagamentos antigos são vinculados a ela para o saldo por parcela continuar batendo.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO payable_installments
                (id, payable_id, number, due_date, amount, paid_amount, created_at)
            SELECT
                lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))), 2) || '-a' ||
                substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
                id, 1, due_date, amount, coalesce(paid_amount, 0), created_at
            FROM purchase_payables
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE payable_payments
            SET installment_id = (
                SELECT installment.id
                FROM payable_installments AS installment
                WHERE installment.payable_id = payable_payments.payable_id
                ORDER BY installment.number
                LIMIT 1
            )
            """
        )
    )
    connection.execute(
        sa.text("UPDATE purchase_payables SET payment_terms = 'À vista' WHERE payment_terms IS NULL")
    )


def downgrade() -> None:
    with op.batch_alter_table("payable_payments") as batch_op:
        batch_op.drop_constraint("fk_payable_payments_installment", type_="foreignkey")
        batch_op.drop_index("ix_payable_payments_installment_id")
        batch_op.drop_column("installment_id")
    op.drop_index("ix_payable_installments_payable_number", table_name="payable_installments")
    op.drop_index("ix_payable_installments_payable_id", table_name="payable_installments")
    op.drop_table("payable_installments")
    with op.batch_alter_table("purchase_payables") as batch_op:
        batch_op.drop_column("payment_terms")
        batch_op.drop_column("interval_days")
        batch_op.drop_column("first_due_days")
        batch_op.drop_column("installment_count")
        batch_op.drop_column("payment_type")
    with op.batch_alter_table("purchase_quotes") as batch_op:
        batch_op.drop_column("interval_days")
        batch_op.drop_column("first_due_days")
        batch_op.drop_column("installment_count")
        batch_op.drop_column("payment_type")
