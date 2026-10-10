from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_quote,
    cancel_purchase,
    close_purchase_balance,
    create_purchase,
    delete_purchase,
    get_purchase,
    place_order,
    receive_purchase_in_full,
    receive_purchase,
    select_quote,
    settle_payable,
)
from app.models import MovementType, Product, PurchaseCase, PurchaseDeletion, StockMovement
from app.schemas.common import (
    PayableUpdate,
    PurchaseCancelRequest,
    PurchaseCloseRequest,
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
)


def _actor() -> SimpleNamespace:
    """Route functions take the authenticated user; tests only need id and name."""
    return SimpleNamespace(id="user-qa", full_name="QA")


def _ordered_purchase(db: Session, user: SimpleNamespace) -> PurchaseOut:
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor A",
            supplier_order_number="PED-123",
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
    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A",
            total=130,
            delivery_days=12,
            item_costs={line.id: Decimal("26")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    return place_order(purchase.id, db, user)


def test_negotiation_receiving_links_product_and_updates_stock_once(db: Session) -> None:
    user = _actor()
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
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="P-2", description="Peça teste", quantity=1)]),
        db,
        user,
    )
    purchase = cancel_purchase(
        purchase.id, PurchaseCancelRequest(reason="Compra de teste cancelada"), db, user
    )
    assert purchase.status == "cancelled"
    assert purchase.cancel_reason == "Compra de teste cancelada"
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


def test_draft_purchase_is_deleted_with_immutable_audit_record(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor Rascunho",
            items=[
                PurchaseItemCreate(
                    sku="P-9", description="Peça em rascunho", quantity=2, unit_cost=Decimal("10")
                )
            ],
        ),
        db,
        user,
    )
    number = purchase.number
    record = delete_purchase(purchase.id, "Criada por engano", db, user)

    assert record.number == number
    assert record.supplier_name == "Fornecedor Rascunho"
    assert "P-9" in record.items_summary
    assert db.scalar(select(func.count(PurchaseCase.id))) == 0
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 1


def test_delete_is_blocked_once_the_order_has_effects(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)

    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, None, db, user)

    assert error.value.status_code == 409
    assert "cotação escolhida" in str(error.value.detail)
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 0


def test_receive_all_marks_every_item_received(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)

    purchase = receive_purchase_in_full(purchase.id, None, True, db, user)

    assert purchase.status == "received"
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None and product.current_stock == Decimal("5.000")
    assert purchase.payables[0].amount == Decimal("130.00")


def test_partial_receipt_cancel_returns_stock_and_closes_the_payable(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-return-0001",
                    quantity=3,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None and product.current_stock == Decimal("3.000")
    assert purchase.payables[0].amount == Decimal("78.00")

    purchase = cancel_purchase(
        purchase.id,
        PurchaseCancelRequest(
            reason="Fornecedor cancelou o saldo restante", resolution="return_received"
        ),
        db,
        user,
    )

    assert purchase.status == "cancelled"
    assert purchase.items[0].returned_quantity == Decimal("3.000")
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("0.000")
    assert purchase.payables[0].status == "cancelled"
    posted = list(db.scalars(select(StockMovement).order_by(StockMovement.created_at)))
    assert [movement.movement_type for movement in posted] == [
        MovementType.purchase_received,
        MovementType.cancellation,
    ]

    # A repeated cancellation must not return the same goods twice.
    with pytest.raises(HTTPException) as error:
        cancel_purchase(
            purchase.id,
            PurchaseCancelRequest(reason="Repetido", resolution="return_received"),
            db,
            user,
        )
    assert error.value.status_code == 409
    assert db.scalar(select(func.count(StockMovement.id))) == 2


def test_close_balance_keeps_received_goods_and_opens_the_payable(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-close-0001",
                    quantity=2,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert purchase.status == "partially_received"

    purchase = close_purchase_balance(
        purchase.id, PurchaseCloseRequest(reason="Fornecedor não entregou o restante"), db, user
    )

    assert purchase.status == "closed"
    assert purchase.closed_at is not None
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("2.000")
    assert purchase.payables[0].amount == Decimal("52.00")

    with pytest.raises(HTTPException) as error:
        close_purchase_balance(purchase.id, PurchaseCloseRequest(reason="De novo"), db, user)
    assert error.value.status_code == 409


def test_expense_payable_is_settled_and_reversed_when_cancelled(db: Session) -> None:
    user = _actor()
    expense = create_purchase(
        PurchaseCreate(
            purchase_type="expense",
            expense_category="Ferramentas",
            expense_amount=Decimal("120.50"),
            supplier_name="Loja X",
            needed_by=datetime(2026, 10, 20, tzinfo=UTC),
        ),
        db,
        user,
    )

    assert expense.status == "received"
    assert len(expense.payables) == 1
    payable = expense.payables[0]
    assert payable.amount == Decimal("120.50")
    assert payable.due_date.date().isoformat() == "2026-11-19"

    settled = settle_payable(expense.id, payable.id, PayableUpdate(payment_method="Pix"), db, user)
    assert settled.status == "paid"
    assert settled.payment_method == "Pix"

    expense = cancel_purchase(
        expense.id, PurchaseCancelRequest(reason="Despesa lançada por engano"), db, user
    )
    refreshed = get_purchase(expense.id, db, user)
    assert refreshed.status == "cancelled"
    assert refreshed.payables[0].status == "cancelled"
