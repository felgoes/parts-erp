from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text import normalize_customer_name
from app.integrations.mercadolivre import ml_support
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.ml_fiscal import (
    automate_order_documents,
)
from app.integrations.mercadolivre.ml_shipping import (
    sync_shipping_status,
)
from app.integrations.mercadolivre.ml_support import (
    ORDER_RESOURCE,
    _account,
    _parse_event_datetime,
    extract_sku,
    is_cancelled,
    is_paid,
    order_shipment_id,
)
from app.models import (
    Customer,
    InvoiceSource,
    InvoiceStatus,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    SalesInvoice,
)
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.after_sale import link_pending_after_sale_cases
from app.services.push_notifications import (
    enqueue_order_status_notification,
    enqueue_sale_notification,
)
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice


def sync_order(db: Session, seller_id: str, resource: str) -> MarketplaceOrder:
    match = ORDER_RESOURCE.fullmatch(resource)
    if not match:
        raise MercadoLivreError("Recurso de pedido inválido")
    order_id = match.group("id")
    account = _account(db, seller_id)
    client = MercadoLivreClient(db, account)
    order = client.get(f"/orders/{order_id}")
    if not isinstance(order, dict) or str(order.get("seller", {}).get("id")) != seller_id:
        raise MercadoLivreError("Pedido não pertence à conta conectada")

    # Horários da plataforma são a fonte de verdade do pedido. O horário de
    # sincronização do ERP continua separado em synchronized_at.
    source_created_at = _parse_event_datetime(str(order.get("date_created") or ""))
    source_updated_at = _parse_event_datetime(str(order.get("last_updated") or ""))

    record = db.scalar(
        select(MarketplaceOrder).where(
            MarketplaceOrder.provider == "mercadolivre",
            MarketplaceOrder.external_order_id == order_id,
        )
    )
    previous_status = record.status if record else None
    previous_shipping_status = record.shipping_status if record else None
    previous_shipping_substatus = record.shipping_substatus if record else None
    previous_invoice_id = record.invoice_id if record else None
    if not record:
        record = MarketplaceOrder(
            provider="mercadolivre",
            external_order_id=order_id,
            seller_id=seller_id,
            status=str(order.get("status", "unknown")),
            payload=order,
        )
        db.add(record)
        db.flush()
    else:
        previous_after_sale_events = (
            record.payload.get("_erp_after_sale_events", [])
            if isinstance(record.payload, dict)
            else []
        )
        previous_destination_address = (
            record.payload.get("_erp_destination_address")
            if isinstance(record.payload, dict)
            else None
        )
        record.status = str(order.get("status", "unknown"))
        record.payload = {
            **order,
            **(
                {"_erp_after_sale_events": previous_after_sale_events}
                if previous_after_sale_events
                else {}
            ),
            **(
                {"_erp_destination_address": previous_destination_address}
                if previous_destination_address
                else {}
            ),
        }
    if source_created_at:
        record.created_at = source_created_at
    if source_updated_at:
        record.payload = {
            **(record.payload or {}),
            "_erp_source_updated_at": source_updated_at.isoformat(),
        }
    has_event = db.scalar(
        select(MarketplaceOrderEvent.id).where(MarketplaceOrderEvent.order_id == record.id).limit(1)
    )
    if previous_status != record.status or not has_event:
        db.add(
            MarketplaceOrderEvent(
                order_id=record.id,
                event_type="order_status",
                status=record.status,
                detail=str(order.get("status_detail") or "")[:255] or None,
                payload={
                    "status": record.status,
                    "status_detail": order.get("status_detail"),
                    "cancel_detail": order.get("cancel_detail"),
                    "order_request": order.get("order_request"),
                    "source_updated_at": source_updated_at.isoformat()
                    if source_updated_at
                    else None,
                },
                created_at=source_updated_at or source_created_at or datetime.now(UTC),
            )
        )
    has_after_sale_event = db.scalar(
        select(MarketplaceOrderEvent.id)
        .where(
            MarketplaceOrderEvent.order_id == record.id,
            MarketplaceOrderEvent.event_type == "after_sale",
        )
        .limit(1)
    )
    if is_cancelled(order) and (previous_status != record.status or not has_after_sale_event):
        cancel_detail = order.get("cancel_detail")
        cancel_detail = cancel_detail if isinstance(cancel_detail, dict) else {}
        reason = str(
            cancel_detail.get("description")
            or cancel_detail.get("reason")
            or order.get("status_detail")
            or "Pedido cancelado no Mercado Livre"
        )[:500]
        db.add(
            MarketplaceOrderEvent(
                order_id=record.id,
                event_type="after_sale",
                status="cancelled",
                detail=reason,
                payload={
                    "kind": "cancellation",
                    "status": "cancelled",
                    "reason": reason,
                    "requested_by": cancel_detail.get("requested_by"),
                },
                created_at=(
                    _parse_event_datetime(
                        str(order.get("date_closed") or order.get("last_updated") or "")
                    )
                    or datetime.now(UTC)
                ),
            )
        )
    shipment_id = order_shipment_id(client, order_id, order)
    record.shipment_id = shipment_id or record.shipment_id
    record.sync_status = "pending"
    record.sync_error = None
    db.commit()
    db.refresh(record)

    # Shipping lifecycle notifications are separate from order/payment changes.
    # Also refresh here so periodic imports repair missed webhooks after downtime.
    if record.shipment_id:
        try:
            sync_shipping_status(db, record, account)
        except Exception as exc:
            record.sync_status = "error"
            record.sync_error = f"Falha ao atualizar rastreio: {exc}"[:1000]
            record.synchronized_at = datetime.now(UTC)
            db.commit()
            raise
        db.commit()
        db.refresh(record)

    config = ml_support._automation_config(db)
    import_orders = config.import_orders if config else True
    automatic_stock = config.automatic_stock if config else True
    try:
        cancelled = is_cancelled(order)
        if import_orders and not record.invoice_id and (is_paid(order) or cancelled):
            item_inputs: list[InvoiceItemCreate] = []
            missing: list[str] = []
            unlinked_products: list[Product] = []
            temporarily_enabled_products: list[Product] = []
            for index, line in enumerate(order.get("order_items", []), start=1):
                sku = extract_sku(line)
                product = db.scalar(select(Product).where(Product.sku == sku)) if sku else None
                if product and cancelled and not product.active:
                    product.active = True
                    temporarily_enabled_products.append(product)
                if not product:
                    if not cancelled:
                        missing.append(sku or str(line.get("item", {}).get("id", "sem SKU")))
                        continue
                    item = line.get("item") if isinstance(line.get("item"), dict) else {}
                    item_id = str(item.get("id") or f"{order_id}-{index}")
                    placeholder_sku = f"ML-NAO-CONCILIADO-{item_id}"[:80]
                    product = db.scalar(select(Product).where(Product.sku == placeholder_sku))
                    if not product:
                        product = Product(
                            sku=placeholder_sku,
                            name=str(item.get("title") or "Item cancelado sem SKU conciliado")[
                                :200
                            ],
                            description=(
                                f"Item do pedido Mercado Livre #{order_id}; conciliação pendente."
                            ),
                            sale_price=Decimal(str(line.get("unit_price", 0))),
                            current_stock=Decimal("0"),
                            minimum_stock=Decimal("0"),
                        )
                        db.add(product)
                        db.flush()
                        unlinked_products.append(product)
                item_inputs.append(
                    InvoiceItemCreate(
                        product_id=product.id,
                        quantity=Decimal(str(line.get("quantity", 1))),
                        unit_price=Decimal(str(line.get("unit_price", 0))),
                    )
                )
            if missing:
                raise MercadoLivreError("SKUs não conciliados: " + ", ".join(missing))

            buyer = order.get("buyer", {})
            buyer_id = str(buyer.get("id", ""))
            customer = db.scalar(select(Customer).where(Customer.marketplace_buyer_id == buyer_id))
            if not customer:
                name = (
                    " ".join(
                        part for part in [buyer.get("first_name"), buyer.get("last_name")] if part
                    )
                    or f"Cliente Mercado Livre {buyer_id}"
                )
                customer = Customer(
                    name=normalize_customer_name(name), marketplace_buyer_id=buyer_id or None
                )
                db.add(customer)
                db.flush()

            invoice = create_invoice(
                db,
                InvoiceCreate(
                    customer_id=customer.id,
                    items=item_inputs,
                    shipping=Decimal("0"),
                    notes=f"Pedido Mercado Livre #{order_id}",
                ),
                source=InvoiceSource.mercadolivre,
                marketplace_order_id=order_id,
            )
            for product in unlinked_products:
                product.active = False
            for product in temporarily_enabled_products:
                product.active = False
            if cancelled:
                cancel_invoice(db, invoice)
            elif automatic_stock:
                confirm_invoice(db, invoice)
            record.invoice_id = invoice.id

        elif record.invoice_id and cancelled:
            invoice = db.get(SalesInvoice, record.invoice_id)
            if invoice and invoice.status != InvoiceStatus.cancelled:
                cancel_invoice(db, invoice)

        if record.invoice_id:
            linked_invoice = db.get(SalesInvoice, record.invoice_id)
            if linked_invoice:
                link_pending_after_sale_cases(db, record, linked_invoice)

        order_created_at = _parse_event_datetime(str(order.get("date_created") or ""))
        if record.invoice_id and order_created_at:
            invoice = db.get(SalesInvoice, record.invoice_id)
            if invoice:
                # Keep the invoice's business date aligned with the original
                # Mercado Livre order, not the later webhook/sync arrival time.
                invoice.issued_at = (
                    order_created_at.replace(tzinfo=UTC)
                    if order_created_at.tzinfo is None
                    else order_created_at.astimezone(UTC)
                )

        record.sync_status = "synced"
        record.sync_error = None
        record.synchronized_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        persisted = db.scalar(
            select(MarketplaceOrder).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.external_order_id == order_id,
            )
        )
        if persisted:
            persisted.sync_status = "error"
            persisted.sync_error = str(exc)[:1000]
            persisted.synchronized_at = datetime.now(UTC)
            db.commit()
            return persisted
        raise

    db.refresh(record)
    enqueue_order_status_notification(
        db, record, previous_status, previous_shipping_status, previous_shipping_substatus
    )
    if record.invoice_id and not previous_invoice_id:
        enqueue_sale_notification(db, record)
    sync_documents = config.sync_documents if config else True
    if record.invoice_id and sync_documents:
        return automate_order_documents(db, record, account)
    return record


def retry_due_orders(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.sync_status == "error",
                MarketplaceOrder.updated_at <= cutoff,
            )
            .limit(10)
        )
    )
    for order in orders:
        try:
            sync_order(db, order.seller_id, f"/orders/{order.external_order_id}")
        except (MercadoLivreError, httpx.RequestError):
            # One unavailable marketplace order must not block retries for the rest.
            continue
    return len(orders)
