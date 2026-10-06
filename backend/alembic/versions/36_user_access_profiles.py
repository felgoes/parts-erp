"""add operational user profiles"""

from collections.abc import Sequence

from alembic import op

revision: str = "36_user_access_profiles"
down_revision: str | None = "35_product_master_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for role in ("stock", "finance", "viewer"):
        op.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}'")
