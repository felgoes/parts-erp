from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
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

_NUMBER_ATTEMPTS = 5


def next_invoice_number(db: Session) -> str:
    """Próximo número da sequência do ano: maior número já usado + 1.

    Não é a contagem de faturas: contar reaproveitaria o número de uma fatura apagada e
    repetiria o número quando duas criações acontecessem juntas. O maior valor do sufixo
    é extraído como número (não como texto), para continuar certo acima de seis dígitos.
    """
    year = datetime.now(UTC).year
    prefix = f"VEN-{year}-"
    highest = db.scalar(
        select(func.max(cast(func.substr(SalesInvoice.number, len(prefix) + 1), Integer))).where(
            SalesInvoice.number.like(f"{prefix}%")
        )
    )
    return f"{prefix}{(highest or 0) + 1:06d}"


def _is_number_collision(error: IntegrityError) -> bool:
    """Distingue a corrida pelo número de um erro de integridade de outra natureza."""
    text = str(getattr(error, "orig", error)).lower()
    return "number" in text and ("unique" in text or "duplicate" in text)


def create_invoice(
    db: Session,
    payload: InvoiceCreate,
    *,
    source: InvoiceSource = InvoiceSource.manual,
    marketplace_order_id: str | None = None,
) -> SalesInvoice:
    # Duas criações simultâneas podem calcular o mesmo número; quem perder a corrida
    # ganha outro número no próximo laço em vez de devolver erro para o operador.
    for _ in range(_NUMBER_ATTEMPTS):
        invoice = _build_invoice(
            db, payload, source=source, marketplace_order_id=marketplace_order_id
        )
        try:
            with db.begin_nested():
                db.add(invoice)
                db.flush()
        except IntegrityError as error:
            if not _is_number_collision(error):
                raise
            continue
        return invoice
    raise HTTPException(
        status_code=503,
        detail="Não foi possível reservar o número da fatura; tente novamente.",
    )


def _build_invoice(
    db: Session,
    payload: InvoiceCreate,
    *,
    source: InvoiceSource,
    marketplace_order_id: str | None,
) -> SalesInvoice:
    """Valida as linhas e monta a fatura (sem número ainda reservado no banco)."""
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
                    StockMovement.idempotency_key == f"invoice:{invoice.id}:item:{item.id}:confirm"
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
