from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password

from app.models import (
    AfterSaleCase,
    AfterSaleCaseItem,
    InvoiceItem,
    InvoiceSource,
    InvoiceStatus,
    MarketplaceOrder,
    MovementType,
    Product,
    SalesInvoice,
    StockMovement,
    User,
    UserRole,
)
from app.schemas.common import (
    AfterSaleInspectIn,
    AfterSaleInspectItemIn,
    AfterSaleReceiveIn,
    AfterSaleReceiveItemIn,
)
from app.services.after_sale import (
    inspect_after_sale_items,
    receive_after_sale_items,
    upsert_after_sale_case,
)
from app.services.stock import move_stock


def _setup_return_case(db: Session):
    product = Product(
        sku="RETURN-1",
        name="Peça de devolução",
        cost_price=Decimal("40.00"),
        current_stock=Decimal("3"),
    )
    db.add(product)
    db.flush()
    invoice = SalesInvoice(
        id="return-invoice",
        number="VEN-RETURN-0001",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.mercadolivre,
        marketplace_order_id="2000001234567890",
        subtotal=Decimal("200.00"),
        discount=Decimal("0"),
        shipping=Decimal("0"),
        total=Decimal("200.00"),
    )
    db.add(invoice)
    db.flush()
    invoice_item = InvoiceItem(
        id="return-invoice-item",
        invoice_id=invoice.id,
        product_id=product.id,
        sku=product.sku,
        description=product.name,
        quantity=Decimal("2"),
        unit_price=Decimal("100.00"),
        total=Decimal("200.00"),
    )
    db.add(invoice_item)
    db.flush()
    sale = move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("-2"),
        movement_type=MovementType.sale,
        reason="Venda ML",
        reference=invoice.id,
        idempotency_key=f"invoice:{invoice.id}:item:{invoice_item.id}:confirm",
        unit_cost=Decimal("40.00"),
    )
    order = MarketplaceOrder(
        id="return-order",
        provider="mercadolivre",
        external_order_id=invoice.marketplace_order_id,
        seller_id="seller-1",
        status="paid",
        sync_status="synced",
        payload={
            "order_items": [
                {
                    "item": {"id": "MLB123"},
                    "seller_sku": product.sku,
                    "quantity": 2,
                }
            ],
            "payments": [],
        },
        invoice_id=invoice.id,
    )
    db.add(order)
    actor = User(
        id="return-operator",
        email="operator@example.test",
        full_name="Operador de teste",
        password_hash=hash_password("qa-only-test-password"),
        role=UserRole.manager,
    )
    db.add(actor)
    db.flush()
    case = upsert_after_sale_case(
        db,
        order,
        {"kind": "return", "status": "opened", "id": "RET-123", "reason": "Cliente desistiu"},
        {"items": [{"item": {"id": "MLB123"}, "quantity": 2}]},
        "RET-123",
    )
    db.flush()
    return product, invoice, invoice_item, sale, order, actor, case


def test_return_receipt_does_not_change_stock_until_inspection_and_restock_is_idempotent(
    db: Session,
) -> None:
    product, _, _, sale, _, actor, case = _setup_return_case(db)
    item = case.items[0]
    assert item.requested_quantity == Decimal("2")
    assert product.current_stock == Decimal("1")

    receive_after_sale_items(
        db,
        case,
        AfterSaleReceiveIn(items=[AfterSaleReceiveItemIn(item_id=item.id, received_quantity=1)]),
        actor,
    )
    assert case.workflow_status == "partially_received"
    assert item.received_quantity == Decimal("1")
    assert product.current_stock == Decimal("1")

    inspection = AfterSaleInspectIn(
        items=[
            AfterSaleInspectItemIn(
                item_id=item.id,
                disposition="restock",
                restock_quantity=1,
                notes="Peça íntegra",
            )
        ]
    )
    inspect_after_sale_items(db, case, inspection, actor)
    inspect_after_sale_items(db, case, inspection, actor)

    movements = list(
        db.scalars(
            select(StockMovement).where(
                StockMovement.movement_type == MovementType.customer_return
            )
        )
    )
    assert len(movements) == 1
    assert movements[0].quantity == Decimal("1")
    assert movements[0].unit_cost == sale.unit_cost == Decimal("40.00")
    assert movements[0].reference == "return-invoice"
    assert product.current_stock == Decimal("2")
    assert item.restocked_quantity == Decimal("1")
    assert item.disposition == "restock"
    assert case.workflow_status == "partially_received"


def test_return_inspection_cannot_restock_more_than_physical_receipt(db: Session) -> None:
    product, _, _, _, _, actor, case = _setup_return_case(db)
    item = case.items[0]
    with pytest.raises(ValueError, match="Registre primeiro o recebimento físico"):
        inspect_after_sale_items(
            db,
            case,
            AfterSaleInspectIn(
                items=[
                    AfterSaleInspectItemIn(
                        item_id=item.id,
                        disposition="restock",
                        restock_quantity=1,
                    )
                ]
            ),
            actor,
        )
    assert product.current_stock == Decimal("1")


def test_duplicate_marketplace_return_updates_existing_case(db: Session) -> None:
    _, _, _, _, order, _, first = _setup_return_case(db)
    repeated = upsert_after_sale_case(
        db,
        order,
        {"kind": "return", "status": "opened", "id": "RET-123", "reason": "Cliente desistiu"},
        {"items": [{"item": {"id": "MLB123"}, "quantity": 2}]},
        "RET-123",
    )
    assert first.id == repeated.id
    assert db.scalar(select(AfterSaleCase).where(AfterSaleCase.external_case_id == "RET-123"))
    assert len(list(db.scalars(select(AfterSaleCaseItem)))) == 1
