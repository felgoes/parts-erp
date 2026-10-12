"""taxa extra (pagamento/processamento) na cotação e no item da compra

Revision ID: 60_purchase_extra_fee
Revises: 59_purchase_document_currency
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "60_purchase_extra_fee"
down_revision: str | None = "59_purchase_document_currency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_quotes") as batch_op:
        batch_op.add_column(
            sa.Column("extras_amount", sa.Numeric(14, 2), nullable=True, server_default="0")
        )
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.add_column(
            sa.Column("extras_amount", sa.Numeric(14, 2), nullable=True, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.drop_column("extras_amount")
    with op.batch_alter_table("purchase_quotes") as batch_op:
        batch_op.drop_column("extras_amount")
