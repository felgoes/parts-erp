"""descrição do gasto na despesa da empresa

Revision ID: 64_purchase_expense_description
Revises: 63_backup_last_success_from_notices
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "64_purchase_expense_description"
down_revision: str | None = "63_backup_last_success_from_notices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.add_column(sa.Column("expense_description", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.drop_column("expense_description")
