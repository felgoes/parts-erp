from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, new_id, now_utc
from app.models.enums import (
    UserRole,
)
from app.models.telemetry import HealthSnapshot, TelemetryEvent  # noqa: F401  (reexportado)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.operator)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_filename: Mapped[str | None] = mapped_column(String(80))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    user: Mapped[User] = relationship()


class PushDevice(TimestampMixin, Base):
    __tablename__ = "push_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(4096), unique=True)
    platform: Mapped[str] = mapped_column(String(20), default="android")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_settings_version: Mapped[int] = mapped_column(default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    user: Mapped[User] = relationship()


class PushPreference(TimestampMixin, Base):
    __tablename__ = "push_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_push_preferences_user_category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sound: Mapped[str] = mapped_column(String(20), default="system")
    user: Mapped[User] = relationship()


class PushNotification(TimestampMixin, Base):
    __tablename__ = "push_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dedupe_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40), default="system", index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ErpSettings(TimestampMixin, Base):
    """Singleton configuration for shared company identity and backup policy."""

    __tablename__ = "erp_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_name: Mapped[str] = mapped_column(String(120), default="Parts ERP")
    company_short_name: Mapped[str] = mapped_column(String(40), default="Parts")
    logo_data_url: Mapped[str | None] = mapped_column(Text)
    backup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    backup_time: Mapped[str] = mapped_column(String(5), default="02:00")
    backup_retention_days: Mapped[int] = mapped_column(default=30)
    backup_destination: Mapped[str] = mapped_column(String(30), default="google_drive")
    drive_client_id: Mapped[str | None] = mapped_column(String(255))
    encrypted_drive_client_secret: Mapped[str | None] = mapped_column(Text)
    encrypted_drive_refresh_token: Mapped[str | None] = mapped_column(Text)
    drive_folder_id: Mapped[str | None] = mapped_column(String(255))
    backup_last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backup_last_status: Mapped[str] = mapped_column(String(30), default="setup_required")
    backup_last_error: Mapped[str | None] = mapped_column(Text)
