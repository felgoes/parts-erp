from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
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
from app.models.catalog import Product
from app.models.telemetry import HealthSnapshot, TelemetryEvent  # noqa: F401  (reexportado)


class Supplier(TimestampMixin, Base):
    """Lightweight supplier registry used to reuse contact, lead time and terms."""

    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    contact: Mapped[str | None] = mapped_column(String(200))
    document: Mapped[str | None] = mapped_column(String(20))
    default_delivery_days: Mapped[int | None] = mapped_column()
    default_payment_terms: Mapped[str | None] = mapped_column(String(200))


class PurchaseCase(TimestampMixin, Base):
    """A procurement cycle, from supplier negotiation through stock receipt."""

    __tablename__ = "purchase_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="negotiating", index=True)
    purchase_type: Mapped[str] = mapped_column(String(30), default="parts", index=True)
    expense_category: Mapped[str | None] = mapped_column(String(80))
    expense_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), index=True
    )
    supplier_order_number: Mapped[str | None] = mapped_column(String(80), index=True)
    purchase_origin: Mapped[str | None] = mapped_column(String(40), index=True)
    document_access_key: Mapped[str | None] = mapped_column(String(44), index=True)
    document_number: Mapped[str | None] = mapped_column(String(60))
    document_series: Mapped[str | None] = mapped_column(String(20))
    issuer_cnpj: Mapped[str | None] = mapped_column(String(20))
    original_currency: Mapped[str | None] = mapped_column(String(3))
    original_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_quote_id: Mapped[str | None] = mapped_column(String(36))
    needed_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    source_import_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    supplier: Mapped["Supplier | None"] = relationship(lazy="joined")
    items: Mapped[list["PurchaseItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )
    quotes: Mapped[list["PurchaseQuote"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="purchase",
        lazy="selectin",
        foreign_keys="PurchaseQuote.purchase_id",
    )
    events: Mapped[list["PurchaseEvent"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )
    attachments: Mapped[list["PurchaseAttachment"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )
    payables: Mapped[list["PurchasePayable"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(24), default="un", server_default="un")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    base_unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    purchase: Mapped[PurchaseCase] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class PurchaseQuote(TimestampMixin, Base):
    __tablename__ = "purchase_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    supplier_name: Mapped[str] = mapped_column(String(200))
    supplier_contact: Mapped[str | None] = mapped_column(String(200))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    allocation_method: Mapped[str] = mapped_column(String(30), default="proportional")
    item_costs: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    delivery_days: Mapped[int | None] = mapped_column()
    payment_type: Mapped[str] = mapped_column(String(20), default="cash")
    installment_count: Mapped[int] = mapped_column(default=1)
    first_due_days: Mapped[int] = mapped_column(default=30)
    interval_days: Mapped[int] = mapped_column(default=30)
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    purchase: Mapped[PurchaseCase] = relationship(
        back_populates="quotes", foreign_keys=[purchase_id]
    )


class PurchaseEvent(Base):
    __tablename__ = "purchase_events"
    __table_args__ = (Index("ix_purchase_events_purchase_created", "purchase_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchase_cases.id", ondelete="CASCADE"))
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("purchase_items.id", ondelete="SET NULL")
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    purchase: Mapped[PurchaseCase] = relationship(back_populates="events")


class PurchaseAttachment(Base):
    __tablename__ = "purchase_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column()
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    purchase: Mapped[PurchaseCase] = relationship(back_populates="attachments")


class PurchasePayable(TimestampMixin, Base):
    """Accounts payable title created by an expense or by receiving a purchase."""

    __tablename__ = "purchase_payables"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_type: Mapped[str] = mapped_column(String(20), default="cash")
    installment_count: Mapped[int] = mapped_column(default=1)
    first_due_days: Mapped[int] = mapped_column(default=0)
    interval_days: Mapped[int] = mapped_column(default=30)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[str | None] = mapped_column(String(60))
    payment_notes: Mapped[str | None] = mapped_column(String(255))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    purchase: Mapped[PurchaseCase] = relationship(back_populates="payables")
    payments: Mapped[list["PayablePayment"]] = relationship(
        cascade="all, delete-orphan", back_populates="payable", lazy="selectin"
    )
    installments: Mapped[list["PayableInstallment"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="payable",
        lazy="selectin",
        order_by="PayableInstallment.number",
    )


class PayableInstallment(Base):
    """Uma parcela do título a pagar, derivada da condição de pagamento combinada."""

    __tablename__ = "payable_installments"
    __table_args__ = (Index("ix_payable_installments_payable_number", "payable_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payable_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_payables.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(default=1)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payable: Mapped[PurchasePayable] = relationship(back_populates="installments")
    payments: Mapped[list["PayablePayment"]] = relationship(
        back_populates="installment", lazy="selectin"
    )

    @property
    def balance(self) -> Decimal:
        return (Decimal(self.amount) - Decimal(self.paid_amount or 0)).quantize(Decimal("0.01"))


class PayablePayment(Base):
    """A single payment recorded against a payable title (partial payments allowed)."""

    __tablename__ = "payable_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payable_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_payables.id", ondelete="CASCADE"), index=True
    )
    installment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payable_installments.id", ondelete="SET NULL"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    method: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payable: Mapped[PurchasePayable] = relationship(back_populates="payments")
    installment: Mapped["PayableInstallment | None"] = relationship(back_populates="payments")


class PurchaseDeletion(Base):
    """Immutable audit record kept after a draft purchase is deleted."""

    __tablename__ = "purchase_deletions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(String(36), index=True)
    number: Mapped[str] = mapped_column(String(30))
    purchase_type: Mapped[str] = mapped_column(String(30))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    items_summary: Mapped[str] = mapped_column(Text, default="")
    children_summary: Mapped[str] = mapped_column(Text, default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    reason: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
