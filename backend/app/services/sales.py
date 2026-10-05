from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    InvoiceItem,
    InvoiceSource,
    InvoiceStatus,
    MovementType,
    Product,
    SalesInvoice,
    StockMovement,
)
from app.schemas.common import InvoiceCreate
from app.services.stock import move_stock


def next_invoice_number(db: Session) -> str:
    year = datetime.now(UTC).year
    count = (
        db.scalar(
            select(func.count(SalesInvoice.id)).where(SalesInvoice.number.like(f"VEN-{year}-%"))
        )
        or 0
    )
    return f"VEN-{year}-{count + 1:06d}"


def create_invoice(
    db: Session,
    payload: InvoiceCreate,
    *,
    source: InvoiceSource = InvoiceSource.manual,
    marketplace_order_id: str | None = None,
) -> SalesInvoice:
    invoice = SalesInvoice(
        number=next_invoice_number(db),
        customer_id=payload.customer_id,
        source=source,
        marketplace_order_id=marketplace_order_id,
        discount=payload.discount,
        shipping=payload.shipping,
        notes=payload.notes,
    )
    subtotal = Decimal("0")
    for requested in payload.items:
        product = db.get(Product, requested.product_id)
        if not product or not product.active:
            raise HTTPException(status_code=422, detail="Produto inválido na fatura")
        unit_price = (
            requested.unit_price if requested.unit_price is not None else product.sale_price
        )
        line_total = Decimal(requested.quantity) * Decimal(unit_price)
        subtotal += line_total
        invoice.items.append(
            InvoiceItem(
                product_id=product.id,
                sku=product.sku,
                description=product.name,
                quantity=requested.quantity,
                unit_price=unit_price,
                total=line_total,
            )
        )
    invoice.subtotal = subtotal
    invoice.total = subtotal - Decimal(payload.discount) + Decimal(payload.shipping)
    if invoice.total < 0:
        raise HTTPException(status_code=422, detail="Total da fatura não pode ser negativo")
    db.add(invoice)
    db.flush()
    return invoice


def confirm_invoice(db: Session, invoice: SalesInvoice) -> SalesInvoice:
    if invoice.status == InvoiceStatus.confirmed:
        return invoice
    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(status_code=409, detail="Somente rascunhos podem ser confirmados")
    for item in invoice.items:
        move_stock(
            db,
            product_id=item.product_id,
            quantity=-Decimal(item.quantity),
            movement_type=MovementType.sale,
            reason=f"Venda {invoice.number}",
            reference=invoice.id,
            idempotency_key=f"invoice:{invoice.id}:item:{item.id}:confirm",
        )
    invoice.status = InvoiceStatus.confirmed
    invoice.issued_at = datetime.now(UTC)
    db.flush()
    return invoice


def cancel_invoice(db: Session, invoice: SalesInvoice) -> SalesInvoice:
    if invoice.status == InvoiceStatus.cancelled:
        return invoice
    if invoice.status == InvoiceStatus.confirmed:
        for item in invoice.items:
            sale_movement = db.scalar(
                select(StockMovement).where(
                    StockMovement.idempotency_key
                    == f"invoice:{invoice.id}:item:{item.id}:confirm"
                )
            )
            move_stock(
                db,
                product_id=item.product_id,
                quantity=Decimal(item.quantity),
                movement_type=MovementType.cancellation,
                reason=f"Cancelamento {invoice.number}",
                reference=invoice.id,
                idempotency_key=f"invoice:{invoice.id}:item:{item.id}:cancel",
                unit_cost=sale_movement.unit_cost if sale_movement else None,
            )
    invoice.status = InvoiceStatus.cancelled
    db.flush()
    return invoice
