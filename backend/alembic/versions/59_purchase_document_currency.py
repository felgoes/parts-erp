"""record document identity, original currency, exchange rate and paid amount"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "59_purchase_document_currency"
down_revision: str | None = "58_purchase_deletion_children"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.add_column(sa.Column("purchase_origin", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("document_access_key", sa.String(length=44), nullable=True))
        batch_op.add_column(sa.Column("document_number", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("document_series", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("issuer_cnpj", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("original_currency", sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column("original_total", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("exchange_rate", sa.Numeric(14, 6), nullable=True))
        batch_op.add_column(sa.Column("paid_amount", sa.Numeric(14, 2), nullable=True))
        batch_op.create_index("ix_purchase_cases_purchase_origin", ["purchase_origin"])
        batch_op.create_index("ix_purchase_cases_document_access_key", ["document_access_key"])


def downgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.drop_index("ix_purchase_cases_document_access_key")
        batch_op.drop_index("ix_purchase_cases_purchase_origin")
        batch_op.drop_column("paid_amount")
        batch_op.drop_column("exchange_rate")
        batch_op.drop_column("original_total")
        batch_op.drop_column("original_currency")
        batch_op.drop_column("issuer_cnpj")
        batch_op.drop_column("document_series")
        batch_op.drop_column("document_number")
        batch_op.drop_column("document_access_key")
        batch_op.drop_column("purchase_origin")
