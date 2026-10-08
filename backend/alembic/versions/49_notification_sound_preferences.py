"""add per-category sound preferences and channel capability"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "49_notification_sound_preferences"
down_revision: str | None = "48_push_preferences_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "push_preferences",
        sa.Column("sound", sa.String(length=20), nullable=False, server_default="system"),
    )
    op.add_column(
        "push_devices",
        sa.Column("sound_settings_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("push_devices", "sound_settings_version")
    op.drop_column("push_preferences", "sound")
