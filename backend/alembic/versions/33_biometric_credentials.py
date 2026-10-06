"""add revocable biometric login credentials"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "33_biometric_credentials"
down_revision: str | None = "32_stock_movement_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biometric_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device_name", sa.String(length=160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_biometric_credentials_token_hash",
        "biometric_credentials",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_biometric_credentials_user_id",
        "biometric_credentials",
        ["user_id"],
    )
    op.create_index(
        "ix_biometric_credentials_expires_at",
        "biometric_credentials",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_biometric_credentials_expires_at", table_name="biometric_credentials")
    op.drop_index("ix_biometric_credentials_user_id", table_name="biometric_credentials")
    op.drop_index("ix_biometric_credentials_token_hash", table_name="biometric_credentials")
    op.drop_table("biometric_credentials")
