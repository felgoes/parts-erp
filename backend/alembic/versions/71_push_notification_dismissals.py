"""store notification dismissals per user"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "71_push_notification_dismissals"
down_revision: str | None = "70_user_financial_summary_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "push_notification_dismissals",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["push_notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "notification_id"),
    )


def downgrade() -> None:
    op.drop_table("push_notification_dismissals")
