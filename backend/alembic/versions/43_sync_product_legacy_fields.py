"""add product fields used by the current product model"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "43_sync_product_legacy_fields"
down_revision: str | None = "42_quote_cost_breakdown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("products")}
    missing = (
        ("mpn", sa.String(120)),
        ("category_id", sa.String(80)),
        ("condition", sa.String(20), {"server_default": "new", "nullable": False}),
        ("warranty", sa.String(160)),
        ("origin", sa.String(80)),
    )
    for definition in missing:
        name, column_type, *options = definition
        if name not in existing:
            op.add_column("products", sa.Column(name, column_type, **(options[0] if options else {})))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for name in ("origin", "warranty", "condition", "category_id", "mpn"):
        if name in {column["name"] for column in inspector.get_columns("products")}:
            op.drop_column("products", name)
