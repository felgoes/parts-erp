import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.text import normalize_customer_name
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    Customer,
    InvoiceDocument,
    InvoiceSource,
    InvoiceStatus,
    MarketplaceAccount,
    MarketplaceConfig,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    ProductMarketplaceListing,
    SalesInvoice,
)
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.after_sale import link_pending_after_sale_cases
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice

ORDER_RESOURCE = re.compile(r"^/orders/(?P<id>\d+)$")
PRINTABLE_LOGISTICS = {"drop_off", "xd_drop_off", "cross_docking", "self_service"}
FINISHED_FISCAL_STATUSES = {"authorized", "not_applicable"}
FINISHED_LABEL_STATUSES = {"downloaded", "completed", "not_applicable"}
TERMINAL_SHIPPING_STATUSES = {"delivered", "returned", "not_delivered", "cancelled", "canceled"}


def _resource_ids(result: dict[str, Any] | list[Any]) -> list[str]:
    if isinstance(result, dict):
        values = result.get("results") or result.get("orders") or []
        if not values and result.get("id"):
            values = [result]
    else:
        values = result
    ids: list[str] = []
    for value in values:
        raw = value.get("id") if isinstance(value, dict) else value
        if raw is not None and str(raw).strip():
            ids.append(str(raw).strip())
    return ids


def extract_invoice_order_ids(invoice: dict[str, Any]) -> set[str]:
    order_ids: set[str] = set()
    candidates = invoice.get("orders") or []
    if invoice.get("order_id"):
        candidates = [*candidates, invoice["order_id"]]
    for candidate in candidates:
        value = candidate.get("id") if isinstance(candidate, dict) else candidate
        if value:
            order_ids.add(str(value))
    for item in invoice.get("items") or []:
        if isinstance(item, dict) and item.get("external_order_id"):
            order_ids.add(str(item["external_order_id"]))
    return order_ids


def extract_sku(item: dict[str, Any]) -> str | None:
    order_item = item.get("item", {})
    if order_item.get("seller_sku"):
        return str(order_item["seller_sku"])
    if order_item.get("seller_custom_field"):
        return str(order_item["seller_custom_field"])
    for attribute in order_item.get("variation_attributes", []):
        if attribute.get("id") in {"SELLER_SKU", "SELLER_CUSTOM_FIELD"}:
            return str(attribute.get("value_name") or attribute.get("value_id") or "") or None
    return None


def is_paid(order: dict[str, Any]) -> bool:
    return order.get("status") == "paid" or any(
        payment.get("status") == "approved" for payment in order.get("payments", [])
    )


def is_cancelled(order: dict[str, Any]) -> bool:
    return str(order.get("status", "")).strip().lower() in {"cancelled", "canceled"}


def _account(db: Session, seller_id: str) -> MarketplaceAccount:
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.seller_id == seller_id,
            MarketplaceAccount.active.is_(True),
        )
    )
    if not account:
        raise MercadoLivreError(f"Conta vendedora {seller_id} não conectada")
    return account


def _automation_config(db: Session) -> MarketplaceConfig | None:
    return db.scalar(select(MarketplaceConfig).limit(1))


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

    record = db.scalar(
        select(MarketplaceOrder).where(
            MarketplaceOrder.provider == "mercadolivre",
            MarketplaceOrder.external_order_id == order_id,
        )
    )
    previous_status = record.status if record else None
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
        record.status = str(order.get("status", "unknown"))
        record.payload = {
            **order,
            **(
                {"_erp_after_sale_events": previous_after_sale_events}
                if previous_after_sale_events
                else {}
            ),
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
                },
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
    shipping = order.get("shipping") or {}
    shipment_id = shipping.get("id") if isinstance(shipping, dict) else None
    record.shipment_id = str(shipment_id) if shipment_id else record.shipment_id
    record.sync_status = "pending"
    record.sync_error = None
    db.commit()
    db.refresh(record)

    config = _automation_config(db)
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
    sync_documents = config.sync_documents if config else True
    if record.invoice_id and sync_documents:
        return automate_order_documents(db, record, account)
    return record


def _store_document(
    db: Session,
    invoice_id: str,
    external_id: str,
    document_type: str,
    filename: str,
    content: bytes,
) -> bool:
    existing = db.scalar(
        select(InvoiceDocument).where(
            InvoiceDocument.invoice_id == invoice_id,
            InvoiceDocument.external_id == external_id,
        )
    )
    if existing:
        return False
    base_dir = Path(get_settings().documents_dir).resolve() / invoice_id
    base_dir.mkdir(parents=True, exist_ok=True)
    path = (base_dir / filename).resolve()
    if base_dir not in path.parents:
        raise MercadoLivreError("Caminho de documento inválido")
    path.write_bytes(content)
    db.add(
        InvoiceDocument(
            invoice_id=invoice_id,
            external_id=external_id,
            document_type=document_type,
            filename=filename,
            storage_path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    )
    return True


def _fiscal_entries(result: Any) -> list[dict[str, Any]]:
    values = result if isinstance(result, list) else [result]
    return [value for value in values if isinstance(value, dict) and value.get("id")]


def sync_invoice_documents(
    db: Session,
    account: MarketplaceAccount,
    order_id: str,
    invoice_id: str,
    order: dict[str, Any] | None = None,
) -> int:
    del order  # Mantido para compatibilidade com chamadas antigas.
    client = MercadoLivreClient(db, account)
    result = client.get(f"/users/{account.seller_id}/invoices/orders/{order_id}")
    saved = 0
    for fiscal in _fiscal_entries(result):
        if str(fiscal.get("status", "")).lower() != "authorized":
            continue
        external_id = str(fiscal.get("id", order_id))
        attributes = fiscal.get("attributes") if isinstance(fiscal.get("attributes"), dict) else {}
        locations = {
            "xml": fiscal.get("xml_location") or attributes.get("xml_location"),
            "pdf": fiscal.get("danfe_location") or attributes.get("danfe_location"),
        }
        for document_type, location in locations.items():
            document_external_id = f"{external_id}:{document_type}"
            existing = db.scalar(
                select(InvoiceDocument).where(
                    InvoiceDocument.invoice_id == invoice_id,
                    InvoiceDocument.external_id == document_external_id,
                )
            )
            if existing or not location:
                continue
            saved += int(
                _store_document(
                    db,
                    invoice_id,
                    document_external_id,
                    document_type,
                    f"nfe-{external_id}.{document_type}",
                    client.download(str(location)),
                )
            )
    db.commit()
    return saved


def issue_and_sync_invoice(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount
) -> None:
    if not record.invoice_id:
        return
    client = MercadoLivreClient(db, account)
    fiscal_entries: list[dict[str, Any]] = []
    config = _automation_config(db)
    auto_issue = (
        config.auto_issue_invoice if config else get_settings().mercadolivre_auto_issue_invoice
    ) and record.status.lower() not in {"cancelled", "canceled"}
    try:
        try:
            result = client.get(
                f"/users/{account.seller_id}/invoices/orders/{record.external_order_id}"
            )
            fiscal_entries = _fiscal_entries(result)
        except MercadoLivreError as exc:
            if exc.status_code != 404:
                raise

        if not fiscal_entries and auto_issue:
            record.fiscal_status = "requesting"
            db.commit()
            result = client.post(
                f"/users/{account.seller_id}/invoices/orders",
                {"orders": [int(record.external_order_id)]},
            )
            fiscal_entries = _fiscal_entries(result)

        statuses = {str(item.get("status", "pending")).lower() for item in fiscal_entries}
        first_id = next((item.get("id") for item in fiscal_entries if item.get("id")), None)
        if first_id:
            record.external_invoice_id = str(first_id)
        if "authorized" in statuses:
            sync_invoice_documents(db, account, record.external_order_id, str(record.invoice_id))
            record.fiscal_status = "authorized"
        elif statuses:
            record.fiscal_status = sorted(statuses)[0]
        else:
            record.fiscal_status = "pending"
        record.fiscal_error = None
    except MercadoLivreError as exc:
        record.fiscal_status = "error"
        record.fiscal_error = str(exc)[:1000]


def sync_shipping_label(db: Session, record: MarketplaceOrder, account: MarketplaceAccount) -> None:
    if not record.invoice_id:
        return
    if not record.shipment_id:
        record.label_status = "waiting_shipment"
        record.label_error = None
        return
    client = MercadoLivreClient(db, account)
    try:
        shipment = client.get(
            f"/shipments/{record.shipment_id}", extra_headers={"x-format-new": "true"}
        )
        if not isinstance(shipment, dict):
            raise MercadoLivreError("Resposta de envio inválida")
        record.shipping_status = str(shipment.get("status") or "unknown")
        sync_shipping_history(db, record, account)

        # Depois que o pedido já foi entregue/devolvido, a janela operacional
        # da etiqueta foi encerrada. Não devemos mostrar "Aguardando envio"
        # indefinidamente só porque a etiqueta não foi arquivada pelo ERP.
        # Se ela já estiver anexada, preservamos o status "Baixada".
        if record.shipping_status.lower() in TERMINAL_SHIPPING_STATUSES:
            has_label = db.scalar(
                select(InvoiceDocument.id).where(
                    InvoiceDocument.invoice_id == record.invoice_id,
                    InvoiceDocument.document_type == "label_pdf",
                )
            )
            if not has_label:
                record.label_status = "completed"
                record.label_error = None
            return

        logistic_value = shipment.get("logistic")
        logistic: dict[str, Any] = logistic_value if isinstance(logistic_value, dict) else {}
        logistic_type = str(shipment.get("logistic_type") or logistic.get("type") or "")
        mode = str(shipment.get("mode") or logistic.get("mode") or "")
        if mode != "me2" or logistic_type not in PRINTABLE_LOGISTICS:
            record.label_status = "not_applicable"
            record.label_error = None
            return
        if record.shipping_status != "ready_to_ship" or str(shipment.get("substatus")) not in {
            "ready_to_print",
            "printed",
        }:
            record.label_status = "waiting"
            record.label_error = None
            return
        if get_settings().mercadolivre_label_format.lower() != "pdf":
            raise MercadoLivreError("Apenas etiquetas PDF são suportadas nesta versão")
        _store_document(
            db,
            str(record.invoice_id),
            f"shipment:{record.shipment_id}:label_pdf",
            "label_pdf",
            f"etiqueta-{record.shipment_id}.pdf",
            client.download(
                f"/shipment_labels?shipment_ids={record.shipment_id}&response_type=pdf"
            ),
        )
        record.label_status = "downloaded"
        record.label_error = None
    except MercadoLivreError as exc:
        record.label_status = "error"
        record.label_error = str(exc)[:1000]


def sync_shipping_history(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount
) -> None:
    """Import the shipment timeline exposed by Mercado Livre's history endpoint."""
    if not record.shipment_id:
        return
    client = MercadoLivreClient(db, account)
    try:
        result = client.get(
            f"/shipments/{record.shipment_id}/history",
            extra_headers={"x-format-new": "true"},
        )
    except MercadoLivreError:
        return
    entries: Any
    if isinstance(result, list):
        entries = result
    elif isinstance(result, dict):
        entries = result.get("history") or result.get("events") or result.get("results") or []
    else:
        entries = []
    if not isinstance(entries, list):
        return
    existing = list(
        db.scalars(
            select(MarketplaceOrderEvent).where(
                MarketplaceOrderEvent.order_id == record.id,
                MarketplaceOrderEvent.event_type == "shipment_status",
            )
        )
    )
    known = {
        (
            event.status,
            event.detail,
            str((event.payload or {}).get("source_date") or ""),
        )
        for event in existing
    }
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("shipment_status") or "").strip()
        if not status:
            continue
        substatus = item.get("substatus") or item.get("sub_status")
        detail = (
            str(substatus or item.get("detail") or item.get("description") or "").strip() or None
        )
        source_date = str(
            item.get("date") or item.get("created_at") or item.get("updated_at") or ""
        ).strip()
        key = (status, detail, source_date)
        if key in known:
            continue
        payload = dict(item)
        payload["source_date"] = source_date
        db.add(
            MarketplaceOrderEvent(
                order_id=record.id,
                event_type="shipment_status",
                status=status,
                detail=detail,
                payload=payload,
                created_at=_parse_event_datetime(source_date) or datetime.now(UTC),
            )
        )
        known.add(key)
    db.commit()


def _parse_event_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def automate_order_documents(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount | None = None
) -> MarketplaceOrder:
    if not record.invoice_id:
        return record
    connected_account = account or _account(db, record.seller_id)
    issue_and_sync_invoice(db, record, connected_account)
    config = _automation_config(db)
    download_label = (
        config.auto_download_label if config else get_settings().mercadolivre_auto_download_label
    )
    if download_label:
        sync_shipping_label(db, record, connected_account)
    record.automation_updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    return record


def retry_pending_automations(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.invoice_id.is_not(None),
                or_(
                    MarketplaceOrder.automation_updated_at.is_(None),
                    MarketplaceOrder.automation_updated_at <= cutoff,
                ),
                (
                    MarketplaceOrder.fiscal_status.not_in(FINISHED_FISCAL_STATUSES)
                    | MarketplaceOrder.label_status.not_in(FINISHED_LABEL_STATUSES)
                ),
            )
            .limit(20)
        )
    )
    for order in orders:
        automate_order_documents(db, order)
    return len(orders)


def sync_products(db: Session, account: MarketplaceAccount) -> int:
    client = MercadoLivreClient(db, account)
    imported = 0
    offset = 0
    while True:
        result = client.get(f"/users/{account.seller_id}/items/search?offset={offset}&limit=50")
        ids = _resource_ids(result)
        if not ids:
            break
        for external_id in ids:
            detail = client.get(f"/items/{external_id}")
            if not isinstance(detail, dict):
                continue
            sku = str(
                detail.get("seller_sku")
                or detail.get("seller_custom_field")
                or next(
                    (
                        attribute.get("value_name")
                        for attribute in detail.get("attributes", [])
                        if attribute.get("id") in {"SELLER_SKU", "SELLER_CUSTOM_FIELD"}
                        and attribute.get("value_name")
                    ),
                    "",
                )
                or f"ML-{external_id}"
            )[:80]
            product = db.scalar(select(Product).where(Product.sku == sku))
            if not product and sku != f"ML-{external_id}":
                product = db.scalar(select(Product).where(Product.sku == f"ML-{external_id}"))
                if product:
                    product.sku = sku
            if not product:
                product = Product(sku=sku, name=str(detail.get("title") or sku))
                db.add(product)
                db.flush()
            product.name = str(detail.get("title") or product.name)[:200]
            product.description = detail.get("description") or product.description
            product.sale_price = Decimal(str(detail.get("price") or product.sale_price or 0))
            product.current_stock = Decimal(str(detail.get("available_quantity") or 0))
            product.active = str(detail.get("status", "active")) == "active"
            pictures = [
                picture.get("secure_url") or picture.get("url")
                for picture in detail.get("pictures", [])
                if isinstance(picture, dict) and (picture.get("secure_url") or picture.get("url"))
            ]
            listing = db.scalar(
                select(ProductMarketplaceListing).where(
                    ProductMarketplaceListing.provider == "mercadolivre",
                    ProductMarketplaceListing.external_item_id == external_id,
                )
            )
            if not listing:
                listing = ProductMarketplaceListing(
                    product_id=product.id,
                    provider="mercadolivre",
                    external_item_id=external_id,
                    images=pictures,
                    payload=detail,
                )
                db.add(listing)
            listing.product_id = product.id
            listing.title = str(detail.get("title") or product.name)[:200]
            listing.permalink = detail.get("permalink")
            listing.thumbnail = detail.get("thumbnail")
            listing.images = pictures
            listing.marketplace_price = Decimal(str(detail.get("price") or 0))
            listing.available_quantity = Decimal(str(detail.get("available_quantity") or 0))
            listing.sold_quantity = int(detail.get("sold_quantity") or 0)
            try:
                visits_result = MercadoLivreClient(db, account).get(
                    f"/visits/items?ids={external_id}"
                )
                if isinstance(visits_result, dict):
                    listing.visits = int(visits_result.get(external_id) or 0)
            except MercadoLivreError:
                # Métricas podem não estar habilitadas para todos os tipos de anúncio.
                pass
            listing.status = str(detail.get("status") or "unknown")
            listing.payload = detail
            listing.synchronized_at = datetime.now(UTC)
            imported += 1
        db.commit()
        offset += len(ids)
        if len(ids) < 50:
            break
    return imported


def sync_product_stock(db: Session, product: Product) -> int:
    account = db.scalar(
        select(MarketplaceAccount)
        .where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.active.is_(True),
        )
        .limit(1)
    )
    if not account:
        return 0
    client = MercadoLivreClient(db, account)
    updated = 0
    for listing in db.scalars(
        select(ProductMarketplaceListing).where(
            ProductMarketplaceListing.product_id == product.id,
            ProductMarketplaceListing.provider == "mercadolivre",
        )
    ):
        result = client.put(
            f"/items/{listing.external_item_id}",
            {"available_quantity": max(0, int(product.current_stock))},
        )
        listing.available_quantity = product.current_stock
        listing.payload = result if isinstance(result, dict) else listing.payload
        listing.synchronized_at = datetime.now(UTC)
        updated += 1
    db.commit()
    return updated


def sync_all(db: Session, account: MarketplaceAccount) -> dict[str, int]:
    products = sync_products(db, account)
    orders = 0
    offset = 0
    synchronized_ids: set[str] = set()
    while True:
        result = MercadoLivreClient(db, account).get(
            f"/orders/search?seller={account.seller_id}&offset={offset}&limit=50"
        )
        ids = _resource_ids(result)
        if not ids:
            break
        for order_id in ids:
            sync_order(db, account.seller_id, f"/orders/{order_id}")
            synchronized_ids.add(order_id)
            orders += 1
        offset += len(ids)
        if len(ids) < 50:
            break
    # Retry known orders without an invoice as well. This backfills cancelled
    # orders already received by webhook before invoice generation was supported.
    missing_invoice_ids = list(
        db.scalars(
            select(MarketplaceOrder.external_order_id).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.seller_id == account.seller_id,
                MarketplaceOrder.invoice_id.is_(None),
            )
        )
    )
    for order_id in missing_invoice_ids:
        if order_id in synchronized_ids:
            continue
        sync_order(db, account.seller_id, f"/orders/{order_id}")
        orders += 1
    return {"products": products, "orders": orders}


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
            .limit(50)
        )
    )
    for order in orders:
        sync_order(db, order.seller_id, f"/orders/{order.external_order_id}")
    return len(orders)
