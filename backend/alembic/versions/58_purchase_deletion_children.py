"""record which related records were removed with a deleted purchase"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "58_purchase_deletion_children"
down_revision: str | None = "57_payment_installments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_deletions") as batch_op:
        batch_op.add_column(
            sa.Column("children_summary", sa.Text(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_deletions") as batch_op:
        batch_op.drop_column("children_summary")
