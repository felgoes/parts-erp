"""add configurable study commission default"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "72_study_commission_default"
down_revision: str | None = "71_push_notification_dismissals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "marketplace_config",
        sa.Column(
            "study_default_commission_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="16",
        ),
    )


def downgrade() -> None:
    op.drop_column("marketplace_config", "study_default_commission_pct")
