"""Configuração compartilhada do assistente.

Revision ID: 66_assistant_configuration
Revises: 65_assistant_conversations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "66_assistant_configuration"
down_revision: str | None = "65_assistant_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_configuration",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 'shared'", name="ck_assistant_configuration_singleton"),
    )


def downgrade() -> None:
    op.drop_table("assistant_configuration")
