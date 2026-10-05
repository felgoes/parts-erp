from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_quote,
    cancel_purchase,
    create_purchase,
    place_order,
    receive_purchase,
    select_quote,
)
from app.models import MovementType, Product, StockMovement
from app.schemas.common import (
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
)


def test_negotiation_receiving_links_product_and_updates_stock_once(db: Session) -> None:
    user = SimpleNamespace(full_name="QA")
    purchase = create_purchase(
        PurchaseCreate(
            notes="Confirmar compatibilidade antes de fechar",
            items=[
                PurchaseItemCreate(
                    sku="LR174890",
                    description="Kit membrana Tiggo",
                    quantity=5,
                    unit_cost=Decimal("24.90"),
                )
            ],
        ),
        db,
        user,
    )
    assert purchase.status == "negotiating"
    assert len(purchase.items) == 1
    line = purchase.items[0]

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A",
            total=150,
            delivery_days=12,
            item_costs={line.id: Decimal("30")},
        ),
        db,
        user,
    )
    quote_a = purchase.quotes[0]
    assert PurchaseOut.model_validate(purchase).quotes[0].item_costs[line.id] == Decimal("30")
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor B",
            total=130,
            delivery_days=20,
            item_costs={line.id: Decimal("26")},
        ),
        db,
        user,
    )
    quote_b = next(quote for quote in purchase.quotes if quote.supplier_name == "Fornecedor B")
    purchase = select_quote(purchase.id, quote_b.id, db, user)
    assert purchase.status == "approved"
    assert purchase.selected_quote_id == quote_b.id
    assert purchase.items[0].unit_cost == Decimal("26.00")
    assert quote_a.id != quote_b.id

    purchase = place_order(purchase.id, db, user)
    assert purchase.status == "ordered"

    first_receipt = PurchaseReceive(
        items=[
            PurchaseReceiveItem(
                item_id=line.id,
                receipt_id="receipt-test-batch-0001",
                quantity=3,
                create_product=True,
            )
        ]
    )
    purchase = receive_purchase(purchase.id, first_receipt, db, user)
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None
    assert product.current_stock == Decimal("3.000")
    assert purchase.status == "partially_received"

    # A retried request uses the same receipt id and must not post stock twice.
    purchase = receive_purchase(purchase.id, first_receipt, db, user)
    assert product.current_stock == Decimal("3.000")
    assert purchase.items[0].received_quantity == Decimal("3.000")

    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-batch-0002",
                    quantity=2,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert purchase.status == "received"
    assert product.current_stock == Decimal("5.000")
    assert db.scalar(select(func.count(StockMovement.id))) == 2
    assert all(
        movement.movement_type == MovementType.purchase_received
        for movement in db.scalars(select(StockMovement))
    )


def test_cancelled_purchase_cannot_be_received(db: Session) -> None:
    user = SimpleNamespace(full_name="QA")
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="P-2", description="Peça teste", quantity=1)]),
        db,
        user,
    )
    purchase = cancel_purchase(purchase.id, db, user)
    assert purchase.status == "cancelled"
    with pytest.raises(HTTPException) as error:
        receive_purchase(
            purchase.id,
            PurchaseReceive(
                items=[
                    PurchaseReceiveItem(
                        item_id=purchase.items[0].id,
                        receipt_id="receipt-test-cancel-0001",
                        quantity=1,
                        create_product=True,
                    )
                ]
            ),
            db,
            user,
        )
    assert error.value.status_code == 409
    assert db.scalar(select(func.count(StockMovement.id))) == 0
