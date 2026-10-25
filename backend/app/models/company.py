from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, now_utc
from app.models.users import User


class CompanyProfile(TimestampMixin, Base):
    """The single operational-company profile used by studies and import costs."""

    __tablename__ = "company_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    manual_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class CompanyProfileVersion(Base):
    """Immutable revision retained for administration and study auditability."""

    __tablename__ = "company_profile_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    manual_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    changed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=now_utc, nullable=False)

    profile: Mapped[CompanyProfile] = relationship()
    changed_by: Mapped[User | None] = relationship()
