"""add versioned company profile"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "73_company_profile"
down_revision: str | None = "72_study_commission_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("manual_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "company_profile_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("manual_fields", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("changed_by_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_company_profile_versions_profile_id",
        "company_profile_versions",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_profile_versions_profile_id")
    op.drop_table("company_profile_versions")
    op.drop_table("company_profiles")
