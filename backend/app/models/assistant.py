"""Persistent, per-user assistant conversations."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
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
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    __mapper_args__ = {"version_id_col": revision}
