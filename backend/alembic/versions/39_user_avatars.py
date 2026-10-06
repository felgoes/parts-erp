"""store user profile avatar filename"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "39_user_avatars"
down_revision: str | None = "38_marketplace_shipping_substatus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_filename", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_filename")
