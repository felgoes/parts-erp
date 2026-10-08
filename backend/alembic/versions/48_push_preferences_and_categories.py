"""categorize push history and add per-user preferences"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "48_push_preferences_categories"
down_revision: str | None = "47_normalize_marketplace_tracking_times"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("push_notifications", sa.Column("category", sa.String(length=40), nullable=False, server_default="system"))
    op.create_index("ix_push_notifications_category", "push_notifications", ["category"])
    op.create_table(
        "push_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category", name="uq_push_preferences_user_category"),
    )
    op.create_index("ix_push_preferences_user_id", "push_preferences", ["user_id"])
    op.create_index("ix_push_preferences_category", "push_preferences", ["category"])


def downgrade() -> None:
    op.drop_index("ix_push_preferences_category", table_name="push_preferences")
    op.drop_index("ix_push_preferences_user_id", table_name="push_preferences")
    op.drop_table("push_preferences")
    op.drop_index("ix_push_notifications_category", table_name="push_notifications")
    op.drop_column("push_notifications", "category")
