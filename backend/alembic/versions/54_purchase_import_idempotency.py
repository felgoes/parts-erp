"""make imported purchase confirmations idempotent"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "54_purchase_import_idempotency"
down_revision: str | None = "53_purchase_event_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.add_column(sa.Column("source_import_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_purchase_cases_source_import_id", ["source_import_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("purchase_cases") as batch_op:
        batch_op.drop_index("ix_purchase_cases_source_import_id")
        batch_op.drop_column("source_import_id")
