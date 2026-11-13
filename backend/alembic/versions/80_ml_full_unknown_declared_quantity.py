from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "80_ml_full_unknown_declared_quantity"
down_revision: str | None = "79_ml_full_sync_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ml_full_shipment_items") as batch_op:
        batch_op.alter_column(
            "declared_quantity",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    op.execute("UPDATE ml_full_shipment_items SET declared_quantity = 0 WHERE declared_quantity IS NULL")
    with op.batch_alter_table("ml_full_shipment_items") as batch_op:
        batch_op.alter_column(
            "declared_quantity",
            existing_type=sa.Integer(),
            nullable=False,
        )
