"""cache complete vehicle brand and model catalogs"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "75_vehicle_catalog_cache"
down_revision: str | None = "74_vehicle_market"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_catalog_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("cache_key", sa.String(160), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "kind",
            "cache_key",
            name="uq_vehicle_catalog_cache_kind_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("vehicle_catalog_cache")
