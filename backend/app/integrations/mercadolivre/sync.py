import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    Customer,
    InvoiceDocument,
    InvoiceSource,
    MarketplaceAccount,
    MarketplaceOrder,
    Product,
)
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.sales import confirm_invoice, create_invoice

ORDER_RESOURCE = re.compile(r"^/orders/(?P<id>\d+)$")

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


def _account(db: Session, seller_id: str) -> MarketplaceAccount:
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.seller_id == seller_id,
            MarketplaceAccount.active.is_(True),
        )
    )
    if not account:
        raise MercadoLivreError(f"Conta vendedora {seller_id} não conectada")
    return account


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
        select(MarketplaceOrder).where(MarketplaceOrder.external_order_id == order_id)
    )
    if not record:
        record = MarketplaceOrder(
            external_order_id=order_id,
            seller_id=seller_id,
            status=str(order.get("status", "unknown")),
            payload=order,
        )
        db.add(record)
        db.flush()
    else:
        record.status = str(order.get("status", "unknown"))
        record.payload = order
    record.sync_status = "pending"
    record.sync_error = None
    db.commit()
    db.refresh(record)

    try:
        if is_paid(order) and not record.invoice_id:
            item_inputs: list[InvoiceItemCreate] = []
            missing: list[str] = []
            for line in order.get("order_items", []):
                sku = extract_sku(line)
                product = db.scalar(select(Product).where(Product.sku == sku)) if sku else None
                if not product:
                    missing.append(sku or str(line.get("item", {}).get("id", "sem SKU")))
                    continue
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
                customer = Customer(name=name, marketplace_buyer_id=buyer_id or None)
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
            confirm_invoice(db, invoice)
            record.invoice_id = invoice.id

        record.sync_status = "synced"
        record.sync_error = None
        record.synchronized_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        persisted = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.external_order_id == order_id)
        )
        if persisted:
            persisted.sync_status = "error"
            persisted.sync_error = str(exc)[:1000]
            persisted.synchronized_at = datetime.now(UTC)
            db.commit()
            return persisted
        raise

    db.refresh(record)
    if record.invoice_id:
        try:
            sync_invoice_documents(db, account, order_id, record.invoice_id, order=order)
        except MercadoLivreError:
            pass
    return record


def sync_invoice_documents(
    db: Session,
    account: MarketplaceAccount,
    order_id: str,
    invoice_id: str,
    order: dict[str, Any] | None = None,
) -> int:
    client = MercadoLivreClient(db, account)
    result = client.get(f"/users/{account.seller_id}/invoices/orders/{order_id}")
    invoices = result if isinstance(result, list) else [result]
    saved = 0
    base_dir = Path(get_settings().documents_dir).resolve() / invoice_id
    base_dir.mkdir(parents=True, exist_ok=True)
    for fiscal in invoices:
        if not isinstance(fiscal, dict) or str(fiscal.get("status", "")).lower() != "authorized":
            continue
        external_id = str(fiscal.get("id", order_id))
        locations = {
            "xml": fiscal.get("xml_location"),
            "pdf": fiscal.get("danfe_location"),
        }
        for document_type, location in locations.items():
            if not location:
                continue
            existing = db.scalar(
                select(InvoiceDocument).where(
                    InvoiceDocument.invoice_id == invoice_id,
                    InvoiceDocument.external_id == f"{external_id}:{document_type}",
                )
            )
            if existing:
                continue
            content = client.download(str(location))
            digest = hashlib.sha256(content).hexdigest()
            filename = f"nfe-{external_id}.{document_type}"
            path = (base_dir / filename).resolve()
            if base_dir not in path.parents:
                raise MercadoLivreError("Caminho de documento inválido")
            path.write_bytes(content)
            db.add(
                InvoiceDocument(
                    invoice_id=invoice_id,
                    external_id=f"{external_id}:{document_type}",
                    document_type=document_type,
                    filename=filename,
                    storage_path=str(path),
                    sha256=digest,
                )
            )
            saved += 1

    shipment_id = str((order or {}).get("shipping", {}).get("id") or "")
    if shipment_id:
        label_external_id = f"shipment:{shipment_id}:label"
        existing = db.scalar(
            select(InvoiceDocument).where(
                InvoiceDocument.invoice_id == invoice_id,
                InvoiceDocument.external_id == label_external_id,
            )
        )
        if not existing:
            try:
                content = client.download(
                    f"/shipment_labels?shipment_ids={shipment_id}&response_type=pdf"
                )
            except MercadoLivreError:
                content = b""
            if content:
                digest = hashlib.sha256(content).hexdigest()
                filename = f"etiqueta-{shipment_id}.pdf"
                path = (base_dir / filename).resolve()
                if base_dir not in path.parents:
                    raise MercadoLivreError("Invalid document path")
                path.write_bytes(content)
                db.add(
                    InvoiceDocument(
                        invoice_id=invoice_id,
                        external_id=label_external_id,
                        document_type="label",
                        filename=filename,
                        storage_path=str(path),
                        sha256=digest,
                    )
                )
                saved += 1
    db.commit()
    return saved


def sync_products(db: Session, account: MarketplaceAccount) -> int:
    client = MercadoLivreClient(db, account)
    imported = 0
    offset = 0
    while True:
        result = client.get(
            f"/users/{account.seller_id}/items/search?offset={offset}&limit=50"
        )
        ids = _resource_ids(result)
        if not ids:
            break
        for external_id in ids:
            detail = client.get(f"/items/{external_id}")
            if not isinstance(detail, dict):
                continue
            sku = str(detail.get("seller_custom_field") or f"ML-{external_id}")[:80]
            product = db.scalar(select(Product).where(Product.sku == sku))
            if not product:
                product = Product(sku=sku, name=str(detail.get("title") or sku))
                db.add(product)
            product.name = str(detail.get("title") or product.name)[:200]
            product.description = detail.get("description") or product.description
            product.sale_price = Decimal(str(detail.get("price") or product.sale_price or 0))
            product.current_stock = Decimal(str(detail.get("available_quantity") or 0))
            product.active = str(detail.get("status", "active")) == "active"
            imported += 1
        db.commit()
        offset += len(ids)
        if len(ids) < 50:
            break
    return imported


def sync_all(db: Session, account: MarketplaceAccount) -> dict[str, int]:
    products = sync_products(db, account)
    orders = 0
    offset = 0
    while True:
        result = MercadoLivreClient(db, account).get(
            f"/orders/search?seller={account.seller_id}&offset={offset}&limit=50"
        )
        ids = _resource_ids(result)
        if not ids:
            break
        for order_id in ids:
            sync_order(db, account.seller_id, f"/orders/{order_id}")
            orders += 1
        offset += len(ids)
        if len(ids) < 50:
            break
    return {"products": products, "orders": orders}


def retry_due_orders(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.sync_status == "error",
                MarketplaceOrder.updated_at <= cutoff,
            )
            .limit(50)
        )
    )
    count = 0
    for order in orders:
        sync_order(db, order.seller_id, f"/orders/{order.external_order_id}")
        count += 1
    return count
