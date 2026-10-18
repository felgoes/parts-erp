"""Persistent, per-user assistant conversations and shared runtime state."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, new_id, now_utc


class AssistantConversation(TimestampMixin, Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Nova conversa")
    messages: Mapped[list["AssistantMessage"]] = relationship(
        cascade="all, delete-orphan", order_by="AssistantMessage.created_at"
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssistantConfiguration(TimestampMixin, Base):
    """Uma configuração compartilhada; credenciais são cifradas antes de gravar."""

    __tablename__ = "assistant_configuration"
    __table_args__ = (
        CheckConstraint("id = 'shared'", name="ck_assistant_configuration_singleton"),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="shared")
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(160))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    __mapper_args__ = {"version_id_col": revision}


class AssistantUsage(Base):
    """Uma linha por chamada ao provedor, incluindo reservas ainda em andamento."""

    __tablename__ = "assistant_usage"
    __table_args__ = (
        Index("ix_assistant_usage_created", "created_at"),
        Index("ix_assistant_usage_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="reserved")
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssistantPendingAction(Base):
    """Prévia validada que só executa após confirmação explícita do administrador.

    A linha sobrevive à exclusão da conversa: ela é a auditoria da ação, que não é desfeita
    junto com o histórico.
    """

    __tablename__ = "assistant_pending_actions"
    __table_args__ = (
        Index("ix_assistant_pending_conversation", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
