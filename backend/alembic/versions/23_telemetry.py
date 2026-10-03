"""add telemetry and health snapshots

Revision ID: 23_telemetry
Revises: 22a_shopee_config
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "23_telemetry"
down_revision: str | None = "22a_shopee_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_events_name_created", "telemetry_events", ["name", "created_at"])
    op.create_table(
        "health_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("check_name", sa.String(length=60), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_snapshots_checked_at", "health_snapshots", ["checked_at"])


def downgrade() -> None:
    op.drop_index("ix_health_snapshots_checked_at", table_name="health_snapshots")
    op.drop_table("health_snapshots")
    op.drop_index("ix_telemetry_events_name_created", table_name="telemetry_events")
    op.drop_table("telemetry_events")
