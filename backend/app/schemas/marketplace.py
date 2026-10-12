from datetime import datetime

from pydantic import (
    BaseModel,
)

from app.schemas.base import ORMModel
from app.schemas.invoices import InvoiceOut


class MarketplaceOrderOut(ORMModel):
    id: str
    external_order_id: str
    seller_id: str
    status: str
    sync_status: str
    sync_error: str | None
    invoice_id: str | None
    synchronized_at: datetime | None
    created_at: datetime
    provider: str = "mercadolivre"
    shipment_id: str | None = None
    shipping_status: str | None = None
    shipping_substatus: str | None = None
    fiscal_status: str = "pending"
    fiscal_error: str | None = None
    external_invoice_id: str | None = None
    label_status: str = "pending"
    label_error: str | None = None
    automation_updated_at: datetime | None = None
    payload: dict | None = None
    invoice: InvoiceOut | None = None


class MarketplaceOrderEventOut(ORMModel):
    id: str
    order_id: str
    event_type: str
    status: str
    detail: str | None
    payload: dict
    created_at: datetime


class MarketplaceStatus(BaseModel):
    configured: bool
    connected: bool
    seller_id: str | None = None
    nickname: str | None = None
    token_expires_at: datetime | None = None
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class MarketplaceConfigOut(BaseModel):
    client_id: str
    client_secret_configured: bool
    redirect_uri: str
    site_id: str
    import_orders: bool
    automatic_stock: bool
    sync_documents: bool
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class MarketplaceConfigUpdate(BaseModel):
    client_id: str
    client_secret: str | None = None
    redirect_uri: str
    site_id: str = "MLB"
    import_orders: bool = True
    automatic_stock: bool = True
    sync_documents: bool = True
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class ShopeeStatus(BaseModel):
    configured: bool
    connected: bool
    shop_id: str | None = None
    token_expires_at: datetime | None = None


class ShopeeConfigOut(BaseModel):
    partner_id: str
    partner_key_configured: bool
    shop_id: str | None
    redirect_uri: str
    region: str
    import_orders: bool
    automatic_stock: bool
    sync_documents: bool


class ShopeeConfigUpdate(BaseModel):
    partner_id: str
    partner_key: str | None = None
    shop_id: str | None = None
    redirect_uri: str
    region: str = "BR"
    import_orders: bool = True
    automatic_stock: bool = True
    sync_documents: bool
