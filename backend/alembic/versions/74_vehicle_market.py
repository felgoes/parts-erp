"""add idempotent vehicle market publications"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "74_vehicle_market"
down_revision: str | None = "73_company_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_market_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "source",
            "metric",
            "period",
            name="uq_vehicle_market_source_metric_period",
        ),
    )
    op.create_table(
        "vehicle_market_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("record_key", sa.String(64), nullable=False),
        sa.Column("nationality", sa.String(80), nullable=False),
        sa.Column("brand", sa.String(120), nullable=False),
        sa.Column("model", sa.String(160)),
        sa.Column("vehicle_category", sa.String(60), nullable=False),
        sa.Column("year_model", sa.Integer()),
        sa.Column("age_band", sa.String(40)),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(80)),
        sa.Column("source_row_label", sa.Text()),
        sa.UniqueConstraint("record_key", name="uq_vehicle_market_record_key"),
    )
    op.create_index(
        "ix_vehicle_market_records_snapshot_id",
        "vehicle_market_records",
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_market_records_snapshot_id")
    op.drop_table("vehicle_market_records")
    op.drop_table("vehicle_market_snapshots")
