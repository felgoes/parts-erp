"""link purchase history events to items and users"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "53_purchase_event_links"
down_revision: str | None = "52_purchase_item_unit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_events") as batch_op:
        batch_op.add_column(sa.Column("item_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key("fk_purchase_events_item", "purchase_items", ["item_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_purchase_events_user", "users", ["user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("purchase_events") as batch_op:
        batch_op.drop_constraint("fk_purchase_events_user", type_="foreignkey")
        batch_op.drop_constraint("fk_purchase_events_item", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.drop_column("item_id")
