from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
)

from app.schemas.base import ORMModel, UtcModel


class InvoiceItemCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)


class InvoiceCreate(BaseModel):
    customer_id: str | None = None
    items: list[InvoiceItemCreate] = Field(min_length=1)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    shipping: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class InvoiceItemOut(ORMModel):
    id: str
    product_id: str
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class DocumentOut(ORMModel):
    id: str
    document_type: str
    filename: str
    created_at: datetime


class InvoiceCustomerOut(ORMModel):
    name: str
    document: str | None = None
    email: str | None = None
    phone: str | None = None


class InvoiceTrackingEventOut(UtcModel):
    status: str
    detail: str | None
    created_at: datetime


class InvoiceTrackingOut(UtcModel):
    shipment_id: str | None
    destination_address: str | None = None
    status: str | None
    shipping_status: str | None
    shipping_substatus: str | None
    label_status: str | None
    last_update: datetime | None
    last_update_source: Literal["platform", "erp"] = "erp"
    history: list[InvoiceTrackingEventOut]


class InvoiceAfterSaleOut(UtcModel):
    kind: str
    status: str
    reason: str | None = None
    requested_by: str | None = None
    return_id: str | None = None
    payment_status: str | None = None
    refund_amount: Decimal | None = None
    requested_at: datetime | None = None
    history: list[InvoiceTrackingEventOut] = Field(default_factory=list)
    cases: list["AfterSaleCaseOut"] = Field(default_factory=list)


class AfterSaleCaseEventOut(ORMModel):
    event_type: str
    status: str
    detail: str | None = None
    created_at: datetime


class AfterSaleCaseItemOut(ORMModel):
    id: str
    invoice_item_id: str | None
    product_id: str
    sku: str
    description: str
    requested_quantity: Decimal
    received_quantity: Decimal
    inspected_quantity: Decimal
    restocked_quantity: Decimal
    disposition: str
    notes: str | None = None


class AfterSaleCaseOut(ORMModel):
    id: str
    provider: str
    external_case_id: str
    marketplace_order_id: str
    invoice_id: str | None
    kind: str
    workflow_status: str
    marketplace_status: str
    reason: str | None
    requested_by: str | None
    payment_status: str | None
    refund_amount: Decimal | None
    requested_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    items: list[AfterSaleCaseItemOut]
    events: list[AfterSaleCaseEventOut]


class AfterSaleReceiveItemIn(BaseModel):
    item_id: str
    received_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class AfterSaleReceiveIn(BaseModel):
    items: list[AfterSaleReceiveItemIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=500)


class AfterSaleInspectItemIn(BaseModel):
    item_id: str
    restock_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    disposition: Literal["restock", "mixed", "damaged", "discarded"]
    notes: str | None = Field(default=None, max_length=500)


class AfterSaleInspectIn(BaseModel):
    items: list[AfterSaleInspectItemIn] = Field(min_length=1)


class AfterSaleCloseIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class InvoiceOut(ORMModel):
    id: str
    number: str
    customer_id: str | None
    status: str
    source: str
    marketplace_order_id: str | None
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    total: Decimal
    issued_at: datetime | None
    notes: str | None
    created_at: datetime
    items: list[InvoiceItemOut]
    documents: list[DocumentOut]
    tracking: "InvoiceTrackingOut | None" = None
    after_sale: InvoiceAfterSaleOut | None = None
    customer: InvoiceCustomerOut | None = None

    @field_serializer("issued_at")
    def serialize_issued_at(self, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
