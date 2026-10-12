from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_quote,
    create_purchase,
    select_quote,
)
from app.schemas.common import (
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseQuoteCreate,
)
from tests.purchases_fixtures import (
    _actor,
)


def test_quote_total_must_close_with_the_items(db: Session) -> None:
    """P11: a soma dos itens tem de fechar com o total informado da proposta."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)]),
        db,
        user,
    )
    line = purchase.items[0]
    with pytest.raises(HTTPException) as error:
        add_quote(
            purchase.id,
            PurchaseQuoteCreate(
                supplier_name="Fornecedor", total=99, item_costs={line.id: Decimal("10")}
            ),
            db,
            user,
        )
    assert error.value.status_code == 422
    assert "não fecha" in str(error.value.detail)


def test_quote_below_charges_is_rejected(db: Session) -> None:
    """P11: proposta impossível (total menor que frete + impostos − desconto) não é salva."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=1)]),
        db,
        user,
    )
    line = purchase.items[0]
    with pytest.raises(HTTPException) as error:
        add_quote(
            purchase.id,
            PurchaseQuoteCreate(
                supplier_name="Fornecedor",
                total=10,
                freight_amount=Decimal("50"),
                item_costs={line.id: Decimal("1")},
            ),
            db,
            user,
        )
    assert error.value.status_code == 422
    assert "menor que o frete" in str(error.value.detail)


def test_quote_charges_are_spread_across_items(db: Session) -> None:
    """P11: frete, impostos e desconto da cotação chegam rateados ao item."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[
                PurchaseItemCreate(sku="A", description="Peça A", quantity=1),
                PurchaseItemCreate(sku="B", description="Peça B", quantity=3),
            ]
        ),
        db,
        user,
    )
    lines = purchase.items
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor",
            total=60,
            freight_amount=Decimal("20"),
            item_costs={lines[0].id: Decimal("10"), lines[1].id: Decimal("10")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)

    first, second = purchase.items
    assert first.freight_amount == Decimal("5.00")
    assert second.freight_amount == Decimal("15.00")
    assert first.unit_cost == Decimal("15.00")
    assert second.unit_cost == Decimal("15.00")
    assert purchase.total_amount == Decimal("60.00")


def test_selected_quote_can_be_replaced_by_a_new_one(db: Session) -> None:
    """P11: a cotação escolhida não é editada — registra-se outra e escolhe de novo."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)]),
        db,
        user,
    )
    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A", total=20, item_costs={line.id: Decimal("10")}
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    assert purchase.status == "approved"

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor B", total=16, item_costs={line.id: Decimal("8")}
        ),
        db,
        user,
    )
    replacement = next(quote for quote in purchase.quotes if quote.supplier_name == "Fornecedor B")
    purchase = select_quote(purchase.id, replacement.id, db, user)

    assert len(purchase.quotes) == 2
    assert purchase.items[0].unit_cost == Decimal("8.00")
    assert purchase.total_amount == Decimal("16.00")


def test_approved_quote_creates_the_title_with_the_agreed_condition(db: Session) -> None:
    """P12: o título nasce na aprovação, com o total e a condição da cotação vencedora."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            document_date=datetime(2026, 10, 1, tzinfo=UTC),
            items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)],
        ),
        db,
        user,
    )
    assert purchase.payables == []
    line = purchase.items[0]

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor",
            total=200,
            item_costs={line.id: Decimal("100")},
            payment_type="installments",
            installment_count=2,
            first_due_days=30,
            interval_days=30,
        ),
        db,
        user,
    )
    assert purchase.payables == []

    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)

    payable = purchase.payables[0]
    assert payable.amount == Decimal("200.00")
    assert payable.payment_terms == "30/60"
    assert [item.amount for item in payable.installments] == [
        Decimal("100.00"),
        Decimal("100.00"),
    ]
    assert [item.due_date.date().isoformat() for item in payable.installments] == [
        "2026-10-31",
        "2026-11-30",
    ]
