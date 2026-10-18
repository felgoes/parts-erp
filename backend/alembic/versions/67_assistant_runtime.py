"""Orçamento, consumo e confirmações do assistente.

Revision ID: 67_assistant_runtime
Revises: 66_assistant_configuration
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "67_assistant_runtime"
down_revision: str | None = "66_assistant_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_configuration",
        sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True),
    )
    op.create_table(
        "assistant_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("assistant_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reserved_cost_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assistant_usage_user_id", "assistant_usage", ["user_id"])
    op.create_index("ix_assistant_usage_created", "assistant_usage", ["created_at"])
    op.create_index(
        "ix_assistant_usage_user_created", "assistant_usage", ["user_id", "created_at"]
    )
    op.create_table(
        "assistant_pending_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("assistant_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tool_name", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assistant_pending_actions_user_id", "assistant_pending_actions", ["user_id"]
    )
    op.create_index(
        "ix_assistant_pending_conversation",
        "assistant_pending_actions",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_pending_conversation", table_name="assistant_pending_actions")
    op.drop_index("ix_assistant_pending_actions_user_id", table_name="assistant_pending_actions")
    op.drop_table("assistant_pending_actions")
    op.drop_index("ix_assistant_usage_user_created", table_name="assistant_usage")
    op.drop_index("ix_assistant_usage_created", table_name="assistant_usage")
    op.drop_index("ix_assistant_usage_user_id", table_name="assistant_usage")
    op.drop_table("assistant_usage")
    op.drop_column("assistant_configuration", "monthly_budget_usd")
