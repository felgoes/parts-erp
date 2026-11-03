from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import new_id


class AdDailyMetric(Base):
    __tablename__ = "ad_daily_metrics"
    __table_args__ = (
        Index(
            "uq_ad_daily_metrics_account_channel_item_date",
            "account_id",
            "channel",
            "item_id",
            "metric_date",
            unique=True,
        ),
        Index("ix_ad_daily_metrics_date", "metric_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("marketplace_accounts.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30), default="mercadolivre")
    item_id: Mapped[str] = mapped_column(String(80))
    parent_item_id: Mapped[str | None] = mapped_column(String(80))
    metric_date: Mapped[date] = mapped_column(Date)
    visits: Mapped[int | None] = mapped_column(Integer)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_status: Mapped[str] = mapped_column(String(20), default="ok")
