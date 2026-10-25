"""track monthly fleet imports"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "76_vehicle_fleet_import_runs"
down_revision: str | None = "75_vehicle_catalog_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_fleet_import_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_url", sa.String(1000), nullable=False, unique=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("source_rows", sa.Integer()),
        sa.Column("aggregate_count", sa.Integer()),
        sa.Column("total_vehicles", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("vehicle_fleet_import_runs")
