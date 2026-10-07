from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text import normalize_customer_name
from app.integrations.shopee.client import ShopeeClient, ShopeeError
from app.models import (
    Customer,
    InvoiceSource,
    MarketplaceAccount,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    SalesInvoice,
)
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.push_notifications import (
    enqueue_order_status_notification,
    enqueue_sale_notification,
)
from app.services.sales import confirm_invoice, create_invoice


def account_for(db: Session, shop_id: str) -> MarketplaceAccount:
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.provider == "shopee",
            MarketplaceAccount.seller_id == str(shop_id),
            MarketplaceAccount.active.is_(True),
        )
    )
    if not account:
        raise ShopeeError(f"Shop {shop_id} not connected")
    return account


def client_for(account: MarketplaceAccount) -> ShopeeClient:
    return ShopeeClient.from_account(account)


def _platform_datetime(value: Any) -> datetime | None:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, UTC) if timestamp > 0 else None


def sync_product_page(db: Session, client: ShopeeClient, item_ids: list[int]) -> int:
    if not item_ids:
        return 0
    details = client.get("/api/v2/product/get_item_base_info", {"item_id_list": item_ids})
    items = details.get("item_list", []) if isinstance(details, dict) else []
    saved = 0
    for item in items:
        item_id = str(item.get("item_id") or "")
        sku = str(item.get("item_sku") or f"SH-{item_id}")[:80]
        product = db.scalar(select(Product).where(Product.sku == sku))
        if not product:
            product = Product(sku=sku, name=str(item.get("item_name") or sku)[:200])
            db.add(product)
        product.name = str(item.get("item_name") or product.name)[:200]
        product.description = item.get("description") or product.description
        product.active = str(item.get("item_status", "NORMAL")).upper() == "NORMAL"
        db.flush()
        saved += 1
    db.commit()
    return saved


def sync_products(db: Session, account: MarketplaceAccount) -> int:
    client = client_for(account)
    cursor = ""
    imported = 0
    while True:
        data = client.get(
            "/api/v2/product/get_item_list",
            {"offset": 0, "page_size": 100, "item_status": "NORMAL", "cursor": cursor},
        )
        ids = [int(item["item_id"]) for item in data.get("item", []) if item.get("item_id")]
        imported += sync_product_page(db, client, ids)
        cursor = str(data.get("next_cursor") or "")
        if not cursor or not ids:
            break
    return imported


def _sku(line: dict[str, Any]) -> str:
    return str(
        line.get("model_sku") or line.get("item_sku") or f"SH-{line.get('item_id', 'unknown')}"
    )[:80]


def sync_order(db: Session, account: MarketplaceAccount, order_sn: str) -> MarketplaceOrder:
    client = client_for(account)
    data = client.get(
        "/api/v2/order/get_order_detail",
        {
            "order_sn_list": [order_sn],
            "response_optional_fields": "buyer_user_id,item_list,pay_time",
        },
    )
    order = (data.get("order_list") or [None])[0]
    if not isinstance(order, dict):
        raise ShopeeError(f"Order {order_sn} not found")
    record = db.scalar(
        select(MarketplaceOrder).where(
            MarketplaceOrder.provider == "shopee",
            MarketplaceOrder.external_order_id == order_sn,
        )
    )
    status = str(order.get("order_status", "UNKNOWN"))
    source_created_at = _platform_datetime(order.get("create_time"))
    source_updated_at = _platform_datetime(order.get("update_time"))
    previous_status = record.status if record else None
    previous_invoice_id = record.invoice_id if record else None
    if not record:
        record = MarketplaceOrder(
            provider="shopee",
            external_order_id=order_sn,
            seller_id=account.seller_id,
            status=status,
            payload=order,
        )
        db.add(record)
        db.flush()
    else:
        record.status = status
        record.payload = order

    if source_created_at:
        record.created_at = source_created_at
    if source_updated_at:
        record.payload = {
            **(record.payload or {}),
            "_erp_source_updated_at": source_updated_at.isoformat(),
        }
    if previous_status != status:
        db.add(
            MarketplaceOrderEvent(
                order_id=record.id,
                event_type="order_status",
                status=status,
                payload={
                    "status": status,
                    "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
                },
                created_at=source_updated_at or source_created_at or datetime.now(UTC),
            )
        )

    if (
        status not in {"UNPAID", "CANCELLED", "IN_CANCEL", "TO_RETURN", "RECLINED"}
        and not record.invoice_id
    ):
        inputs: list[InvoiceItemCreate] = []
        for line in order.get("item_list", []):
            sku = _sku(line)
            product = db.scalar(select(Product).where(Product.sku == sku))
            if not product:
                product = Product(sku=sku, name=str(line.get("item_name") or sku)[:200])
                db.add(product)
                db.flush()
            quantity = Decimal(
                str(line.get("model_quantity_purchased") or line.get("quantity_purchased") or 1)
            )
            price = Decimal(str(line.get("model_discounted_price") or line.get("item_price") or 0))
            inputs.append(
                InvoiceItemCreate(product_id=product.id, quantity=quantity, unit_price=price)
            )
        buyer_id = str(order.get("buyer_user_id") or "") or None
        customer = (
            db.scalar(select(Customer).where(Customer.marketplace_buyer_id == buyer_id))
            if buyer_id
            else None
        )
        if not customer:
            customer = Customer(
                name=normalize_customer_name(f"Cliente Shopee {buyer_id or order_sn}"),
                marketplace_buyer_id=buyer_id,
            )
            db.add(customer)
            db.flush()
        if inputs:
            invoice = create_invoice(
                db,
                InvoiceCreate(
                    customer_id=customer.id, items=inputs, notes=f"Pedido Shopee #{order_sn}"
                ),
                source=InvoiceSource.shopee,
                marketplace_order_id=f"shopee:{order_sn}",
            )
            confirm_invoice(db, invoice)
            record.invoice_id = invoice.id
    if record.invoice_id and source_created_at:
        invoice = db.get(SalesInvoice, record.invoice_id)
        if invoice:
            invoice.issued_at = source_created_at
    record.sync_status = "synced"
    record.sync_error = None
    record.synchronized_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    enqueue_order_status_notification(db, record, previous_status, None, None)
    if record.invoice_id and not previous_invoice_id:
        enqueue_sale_notification(db, record)
    return record


def sync_all(db: Session, account: MarketplaceAccount) -> dict[str, int]:
    products = sync_products(db, account)
    client = client_for(account)
    end = datetime.now(UTC)
    start = end - timedelta(days=15)
    cursor = ""
    orders = 0
    while True:
        data = client.get(
            "/api/v2/order/get_order_list",
            {
                "time_range_field": "create_time",
                "time_from": int(start.timestamp()),
                "time_to": int(end.timestamp()),
                "page_size": 100,
                "cursor": cursor,
                "order_status": "ALL",
            },
        )
        for item in data.get("order_list", []):
            order_sn = str(item.get("order_sn") or "")
            if order_sn:
                sync_order(db, account, order_sn)
                orders += 1
        cursor = str(data.get("next_cursor") or "")
        if not cursor or not data.get("order_list"):
            break
    return {"products": products, "orders": orders}
