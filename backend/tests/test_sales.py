from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InvoiceStatus, Product, SalesInvoice, StockMovement
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services import sales
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice


def _invoice(db: Session, item: Product):
    return create_invoice(
        db, InvoiceCreate(items=[InvoiceItemCreate(product_id=item.id, quantity=1)])
    )


def test_invoice_number_follows_the_highest_used_and_never_repeats(db: Session) -> None:
    """Apagar uma fatura não devolve o número dela para a próxima."""
    item = product(db)
    prefix = sales.next_invoice_number(db)[:9]
    assert [_invoice(db, item).number, _invoice(db, item).number] == [
        f"{prefix}000001",
        f"{prefix}000002",
    ]

    db.delete(db.scalar(select(SalesInvoice).where(SalesInvoice.number == f"{prefix}000001")))
    db.flush()

    assert _invoice(db, item).number == f"{prefix}000003"
    assert sales.next_invoice_number(db) == f"{prefix}000004"


def test_invoice_number_collision_is_retried_with_the_next_free_number(
    db: Session, monkeypatch
) -> None:
    """Duas criações ao mesmo tempo: quem perde a corrida recebe outro número, sem erro."""
    item = product(db)
    used = [_invoice(db, item).number, _invoice(db, item).number]
    original = sales.next_invoice_number
    attempts = {"count": 0}

    def stale_then_fresh(session: Session) -> str:
        attempts["count"] += 1
        # A primeira tentativa repete um número já usado (a corrida); depois, o livre.
        return used[0] if attempts["count"] == 1 else original(session)

    monkeypatch.setattr(sales, "next_invoice_number", stale_then_fresh)
    recovered = _invoice(db, item)

    assert attempts["count"] == 2
    assert recovered.number not in used
    # A sessão continua utilizável: a fatura recuperada ficou gravada de verdade.
    assert db.scalar(select(func.count(SalesInvoice.id))) == 3


def product(db: Session, stock: str = "10") -> Product:
    value = Product(
        sku="PAST-001",
        name="Pastilha de freio dianteira",
        sale_price=Decimal("149.90"),
        cost_price=Decimal("80"),
        current_stock=Decimal(stock),
        minimum_stock=Decimal("2"),
    )
    db.add(value)
    db.flush()
    return value


def test_confirm_and_cancel_invoice_moves_stock_once(db: Session) -> None:
    item = product(db)
    invoice = create_invoice(
        db,
        InvoiceCreate(items=[InvoiceItemCreate(product_id=item.id, quantity=2)]),
    )

    confirm_invoice(db, invoice)
    confirm_invoice(db, invoice)
    assert invoice.status == InvoiceStatus.confirmed
    assert item.current_stock == Decimal("8")
    assert db.scalar(select(func.count(StockMovement.id))) == 1

    cancel_invoice(db, invoice)
    cancel_invoice(db, invoice)
    assert item.current_stock == Decimal("10")
    assert db.scalar(select(func.count(StockMovement.id))) == 2


def test_invoice_refuses_negative_stock(db: Session) -> None:
    item = product(db, "1")
    invoice = create_invoice(
        db,
        InvoiceCreate(items=[InvoiceItemCreate(product_id=item.id, quantity=2)]),
    )
    with pytest.raises(HTTPException) as exc:
        confirm_invoice(db, invoice)
    assert exc.value.status_code == 409
