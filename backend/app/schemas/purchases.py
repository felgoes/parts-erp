from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from app.schemas.base import ORMModel
from app.schemas.purchase_quotes import PurchaseItemOut, PurchaseQuoteOut


class PurchaseItemCreate(BaseModel):
    product_id: str | None = None
    sku: str = Field(default="", max_length=80)
    description: str = Field(min_length=2, max_length=200)
    unit: str = Field(default="un", min_length=1, max_length=24)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    # P5: taxa de pagamento/processamento cobrada por fora do valor das peças.
    extras_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    # P0: desconto da linha do documento importado. Vira o custo unitário líquido da peça.
    line_discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    # Total que o documento imprime para a linha: manda no fechamento quando existe, porque o
    # papel arredonda o unitário na vitrine (20 × 6,43 = 128,60) e cobra o total exato (128,42).
    line_total_amount: Decimal | None = Field(default=None, ge=0)


class PurchaseItemUpdate(BaseModel):
    """P9: a compra só edita dados da peça — custo, frete, impostos e desconto vivem na cotação."""

    description: str | None = Field(default=None, min_length=2, max_length=200)
    sku: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    quantity: Decimal | None = Field(default=None, gt=0)


class PurchaseUpdate(BaseModel):
    supplier_name: str | None = Field(default=None, max_length=200)
    supplier_id: str | None = None
    supplier_order_number: str | None = Field(default=None, max_length=80)
    document_date: datetime | None = None
    needed_by: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    expense_category: str | None = Field(default=None, max_length=80)
    expense_amount: Decimal | None = Field(default=None, ge=0)


class PurchaseReturnItem(BaseModel):
    item_id: str
    quantity: Decimal = Field(gt=0)
    observation: str | None = Field(default=None, max_length=160)


class PurchaseCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)
    resolution: Literal["keep_received", "return_received"] = "keep_received"
    return_items: list[PurchaseReturnItem] = Field(default_factory=list)


class PurchaseCloseRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact: str | None = Field(default=None, max_length=200)
    document: str | None = Field(default=None, max_length=20)
    default_delivery_days: int | None = Field(default=None, ge=0, le=3650)
    default_payment_terms: str | None = Field(default=None, max_length=200)


class SupplierOut(ORMModel):
    id: str
    name: str
    contact: str | None
    document: str | None
    default_delivery_days: int | None
    default_payment_terms: str | None


class PayableInstallmentOut(ORMModel):
    id: str
    number: int
    due_date: datetime
    amount: Decimal
    paid_amount: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")


class PayableOut(ORMModel):
    id: str
    supplier_name: str | None
    amount: Decimal
    paid_amount: Decimal = Decimal("0")
    due_date: datetime
    payment_terms: str | None = None
    installment_count: int = 1
    installments: list[PayableInstallmentOut] = Field(default_factory=list)
    status: str
    paid_at: datetime | None
    payment_method: str | None
    payment_notes: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


class PayableUpdate(BaseModel):
    due_date: datetime | None = None
    payment_method: str | None = Field(default=None, max_length=60)
    payment_notes: str | None = Field(default=None, max_length=255)
    paid_at: datetime | None = None
    payment_type: Literal["cash", "installments", "entry"] | None = None
    installment_count: int | None = Field(default=None, ge=1, le=36)
    first_due_days: int | None = Field(default=None, ge=0, le=3650)
    interval_days: int | None = Field(default=None, ge=1, le=3650)


class PayablePaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_at: datetime | None = None
    method: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)
    installment_id: str | None = None


class PayablePaymentOut(ORMModel):
    id: str
    amount: Decimal
    paid_at: datetime
    method: str | None
    notes: str | None
    reconciled: bool
    reconciled_at: datetime | None
    reconciled_by_id: str | None
    created_by_id: str | None
    created_at: datetime


class PayableReconcile(BaseModel):
    reconciled: bool = True


class PayableListItem(ORMModel):
    id: str
    purchase_id: str
    purchase_number: str
    purchase_type: str
    purchase_status: str
    expense_category: str | None
    supplier_id: str | None
    supplier_name: str | None
    amount: Decimal
    paid_amount: Decimal
    balance: Decimal
    due_date: datetime
    payment_terms: str | None = None
    installment_count: int = 1
    status: str
    days_overdue: int
    payment_count: int
    reconciled_payment_count: int
    last_payment_at: datetime | None
    created_at: datetime


class PayableDetailOut(PayableListItem):
    payment_type: str = "cash"
    first_due_days: int = 0
    interval_days: int = 30
    payments: list[PayablePaymentOut] = Field(default_factory=list)
    installments: list[PayableInstallmentOut] = Field(default_factory=list)


class PayableAgingBucket(BaseModel):
    label: str
    count: int
    balance: Decimal


class PayableSummary(BaseModel):
    open_balance: Decimal
    overdue_balance: Decimal
    due_next_days_balance: Decimal
    paid_in_period: Decimal
    open_count: int
    overdue_count: int
    partial_count: int
    paid_count: int
    unreconciled_payments: int


class PayableListResponse(BaseModel):
    items: list[PayableListItem]
    summary: PayableSummary
    aging: list[PayableAgingBucket]
    next_days: int


class PayableSupplierReport(BaseModel):
    supplier_name: str
    open_balance: Decimal
    overdue_balance: Decimal
    paid_in_period: Decimal
    titles: int


class PayableMonthReport(BaseModel):
    month: str
    paid: Decimal
    titles: int


class PayableReportResponse(BaseModel):
    period_label: str
    start_date: date
    end_date: date
    summary: PayableSummary
    aging: list[PayableAgingBucket]
    by_supplier: list[PayableSupplierReport]
    by_month: list[PayableMonthReport]


class PurchaseDeletionOut(ORMModel):
    id: str
    number: str
    purchase_type: str
    supplier_name: str | None
    items_summary: str
    children_summary: str = ""
    total_amount: Decimal
    reason: str | None
    user_id: str | None
    created_at: datetime


class PurchaseImportDocument(BaseModel):
    """P0: valores do documento revisado que viram a cotação aceita da compra importada."""

    filename: str = Field(min_length=1, max_length=255)
    total: Decimal | None = Field(default=None, ge=0)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    # P5: taxa de pagamento/processamento cobrada por fora do valor das peças.
    extras_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)


class PurchaseCreate(BaseModel):
    purchase_type: Literal["parts", "expense"] = "parts"
    expense_category: str | None = Field(default=None, max_length=80)
    expense_amount: Decimal | None = Field(default=None, ge=0)
    supplier_name: str | None = Field(default=None, max_length=200)
    supplier_id: str | None = None
    supplier_order_number: str | None = Field(default=None, max_length=80)
    purchase_origin: str | None = Field(default=None, max_length=40)
    document_access_key: str | None = Field(default=None, max_length=44)
    document_number: str | None = Field(default=None, max_length=60)
    document_series: str | None = Field(default=None, max_length=20)
    issuer_cnpj: str | None = Field(default=None, max_length=20)
    original_currency: str | None = Field(default=None, max_length=3)
    original_total: Decimal | None = Field(default=None, ge=0)
    exchange_rate: Decimal | None = Field(default=None, gt=0)
    paid_amount: Decimal | None = Field(default=None, ge=0)
    paid_now: bool = False
    paid_date: datetime | None = None
    paid_method: str | None = Field(default=None, max_length=60)
    document_date: datetime | None = None
    needed_by: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    source_import_id: str | None = Field(default=None, min_length=36, max_length=36)
    import_document: PurchaseImportDocument | None = None
    payment_type: Literal["cash", "installments", "entry"] = "cash"
    installment_count: int = Field(default=1, ge=1, le=36)
    first_due_days: int = Field(default=0, ge=0, le=3650)
    interval_days: int = Field(default=30, ge=1, le=3650)
    items: list[PurchaseItemCreate] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_kind(self) -> "PurchaseCreate":
        if self.purchase_type == "parts" and not self.items:
            raise ValueError("Informe pelo menos uma peça")
        if self.purchase_type == "expense" and (
            not self.expense_category or self.expense_amount is None
        ):
            raise ValueError("Informe a categoria e o valor da despesa")
        if (
            self.original_currency
            and self.original_currency.upper() != "BRL"
            and not self.exchange_rate
        ):
            raise ValueError(
                "Documento em moeda estrangeira exige a cotação usada na conversão para reais."
            )
        return self


class PurchaseReceiveItem(BaseModel):
    item_id: str
    receipt_id: str = Field(min_length=12, max_length=120)
    quantity: Decimal = Field(gt=0)
    product_id: str | None = None
    create_product: bool = False
    observation: str | None = Field(default=None, max_length=160)


class PurchaseReceive(BaseModel):
    items: list[PurchaseReceiveItem] = Field(min_length=1)


class PurchaseEventOut(ORMModel):
    id: str
    item_id: str | None = None
    user_id: str | None = None
    event_type: str
    detail: str
    created_at: datetime


class PurchaseAttachmentOut(ORMModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class PurchaseOut(ORMModel):
    id: str
    number: str
    status: str
    purchase_type: str
    expense_category: str | None
    expense_amount: Decimal | None
    supplier_name: str | None
    supplier_id: str | None = None
    supplier_order_number: str | None = None
    purchase_origin: str | None = None
    document_access_key: str | None = None
    document_number: str | None = None
    document_series: str | None = None
    issuer_cnpj: str | None = None
    original_currency: str | None = None
    original_total: Decimal | None = None
    exchange_rate: Decimal | None = None
    paid_amount: Decimal | None = None
    document_date: datetime | None = None
    selected_quote_id: str | None
    needed_by: datetime | None
    ordered_at: datetime | None
    cancel_reason: str | None = None
    cancelled_at: datetime | None = None
    closed_at: datetime | None = None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    total_amount: Decimal | None = None
    items: list[PurchaseItemOut]
    quotes: list[PurchaseQuoteOut]
    events: list[PurchaseEventOut]
    attachments: list[PurchaseAttachmentOut]
    payables: list[PayableOut] = Field(default_factory=list)
