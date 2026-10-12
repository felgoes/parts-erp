from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    create_purchase,
    delete_purchase,
    receive_purchase,
    receive_purchase_in_full,
    settle_payable,
)
from app.models import (
    MarketStudy,
    MovementType,
    Product,
    PurchaseCase,
    PurchaseDeletion,
    StockMovement,
)
from app.schemas.common import (
    PayableUpdate,
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
)
from app.services.stock import move_stock
from tests.purchases_fixtures import (
    _actor,
    _ordered_purchase,
)


def test_draft_purchase_is_deleted_with_immutable_audit_record(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor Rascunho",
            items=[PurchaseItemCreate(sku="P-9", description="Peça em rascunho", quantity=2)],
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


def test_purchase_with_effects_is_deleted_with_its_children(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)

    record = delete_purchase(purchase.id, "Pedido criado por engano", db, user)

    assert "cotação" in record.children_summary
    assert db.get(PurchaseCase, purchase.id) is None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 1
    # Reenviar não exclui duas vezes: a compra já não existe.
    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, None, db, user)
    assert error.value.status_code == 404


def test_deleting_a_received_purchase_reverses_stock_and_keeps_the_trail(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-delete-0001",
                    quantity=3,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal(
        "3.000"
    )

    record = delete_purchase(purchase.id, "Compra de teste", db, user)

    assert "estorno" in record.children_summary
    assert "título a pagar" in record.children_summary
    assert db.get(PurchaseCase, purchase.id) is None
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal(
        "0.000"
    )
    movements = list(db.scalars(select(StockMovement).order_by(StockMovement.created_at)))
    assert [movement.movement_type for movement in movements] == [
        MovementType.purchase_received,
        MovementType.cancellation,
    ]


def test_deletion_is_blocked_when_the_reversal_would_leave_negative_stock(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-delete-0002",
                    quantity=4,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    product_id = db.scalar(select(Product.id).where(Product.sku == "LR174890"))
    move_stock(
        db,
        product_id=product_id,
        quantity=Decimal("-3"),
        movement_type=MovementType.sale,
        reason="Venda de teste",
        reference="QA",
        idempotency_key="qa-sale-delete-guard",
        unit_cost=Decimal("26.00"),
    )
    db.commit()

    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, "Tentativa", db, user)

    assert error.value.status_code == 409
    assert "Estoque insuficiente" in str(error.value.detail)
    assert db.get(PurchaseCase, purchase.id) is not None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 0


def test_deletion_is_blocked_by_registered_payment(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    purchase = receive_purchase_in_full(purchase.id, None, True, db, user)
    payable = purchase.payables[0]
    settle_payable(purchase.id, payable.id, PayableUpdate(payment_method="Pix"), db, user)

    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, "Com pagamento", db, user)

    assert error.value.status_code == 409
    assert "pagamento" in str(error.value.detail)
    assert db.get(PurchaseCase, purchase.id) is not None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 0


def test_market_study_keeps_existing_and_only_loses_the_link(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[PurchaseItemCreate(sku="P-77", description="Peça estudo", quantity=1)]
        ),
        db,
        user,
    )
    study = MarketStudy(
        id="study-qa-1",
        created_by_id="user-qa",
        search_term="Peça estudo",
        landed_cost=Decimal("10.00"),
        target_margin_pct=Decimal("20.00"),
        marketplace_fee_pct=Decimal("10.00"),
        linked_purchase_id=purchase.id,
    )
    db.add(study)
    db.commit()

    delete_purchase(purchase.id, "Compra ligada a estudo", db, user)

    stored = db.get(MarketStudy, "study-qa-1")
    assert stored is not None
    assert stored.linked_purchase_id is None
