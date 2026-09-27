from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InvoiceStatus, Product, StockMovement
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice


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
