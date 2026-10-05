from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.finance import overview
from app.models import (
    InvoiceItem,
    InvoiceSource,
    InvoiceStatus,
    MovementType,
    Product,
    SalesInvoice,
    StockMovement,
)
from app.services.stock import move_stock


def test_purchase_receipts_use_weighted_average_and_movement_cost_snapshots(
    db: Session,
) -> None:
    product = Product(sku="COST-1", name="Peça de teste", cost_price=Decimal("0"), current_stock=0)
    db.add(product)
    db.flush()

    def receive(qty: int, cost: str, key: str) -> StockMovement:
        return move_stock(
            db,
            product_id=product.id,
            quantity=Decimal(qty),
            movement_type=MovementType.purchase_received,
            reason="Recebimento para teste",
            reference=None,
            idempotency_key=key,
            unit_cost=Decimal(cost),
        )

    first = receive(2, "10", "cost-receipt-1")
    second = receive(2, "20", "cost-receipt-2")
    assert product.current_stock == Decimal("4")
    assert product.cost_price == Decimal("15.00")
    assert first.unit_cost == Decimal("10")
    assert first.movement_value == Decimal("20.00")
    assert second.unit_cost == Decimal("20")
    assert second.movement_value == Decimal("40.00")

    sale = move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("-1"),
        movement_type=MovementType.sale,
        reason="Venda teste",
        reference="invoice-1",
        idempotency_key="cost-sale-1",
    )
    assert sale.unit_cost == Decimal("15.00")
    assert sale.movement_value == Decimal("15.00")

    # Even if the average later changes, cancellation reverses the historical sale cost.
    receive(2, "35", "cost-receipt-3")
    assert product.cost_price == Decimal("23.00")
    reversal = move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("1"),
        movement_type=MovementType.cancellation,
        reason="Devolução teste",
        reference="invoice-1",
        idempotency_key="cost-return-1",
        unit_cost=sale.unit_cost,
    )
    assert reversal.unit_cost == Decimal("15.00")
    assert reversal.movement_value == Decimal("15.00")


def test_finance_overview_reports_inventory_entries_outputs_and_returns(db: Session) -> None:
    today = date.today()
    product = Product(sku="FIN-1", name="Filtro", cost_price=Decimal("12.50"), current_stock=0)
    db.add(product)
    db.flush()
    invoice = SalesInvoice(
        id="invoice-1",
        number="VEN-TEST-000001",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.manual,
        subtotal=Decimal("100"),
        discount=0,
        shipping=0,
        total=Decimal("100"),
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    db.flush()
    invoice_item = InvoiceItem(
        id="item-1",
        invoice_id=invoice.id,
        product_id=product.id,
        sku=product.sku,
        description=product.name,
        quantity=Decimal("2"),
        unit_price=Decimal("50"),
        total=Decimal("100"),
    )
    db.add(invoice_item)
    db.flush()
    move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("4"),
        movement_type=MovementType.purchase_received,
        reason="Entrada compra",
        reference="PO-1",
        idempotency_key="finance-receipt",
        unit_cost=Decimal("12.50"),
    )
    move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("-2"),
        movement_type=MovementType.sale,
        reason="Venda",
        reference="invoice-1",
        idempotency_key=f"invoice:{invoice.id}:item:{invoice_item.id}:confirm",
    )
    move_stock(
        db,
        product_id=product.id,
        quantity=Decimal("1"),
        movement_type=MovementType.cancellation,
        reason="Devolução",
        reference="invoice-1",
        idempotency_key="finance-return",
        unit_cost=Decimal("12.50"),
    )

    result = overview(today, today, db, SimpleNamespace())
    assert result.inventory_units == Decimal("3")
    assert result.inventory_value == Decimal("37.50")
    assert result.inbound_quantity == Decimal("5.000")
    assert result.inbound_value == Decimal("62.50")
    assert result.outbound_quantity == Decimal("2.000")
    assert result.outbound_value == Decimal("25.00")
    assert result.return_quantity == Decimal("1.000")
    assert result.return_value == Decimal("12.50")
    assert result.net_cost_of_goods == Decimal("12.50")
    assert result.unknown_cost_movements == 0
    assert result.unvalued_sales_items == 0
    assert result.gross_margin == Decimal("87.50")
    assert db.scalar(select(Product).where(Product.id == product.id)).cost_price == Decimal("12.50")


def test_finance_does_not_show_complete_margin_without_historical_sale_cost(db: Session) -> None:
    today = date.today()
    product = Product(sku="FIN-2", name="Bomba", cost_price=Decimal("40"), current_stock=0)
    db.add(product)
    db.flush()
    invoice = SalesInvoice(
        id="invoice-without-stock-ledger",
        number="VEN-TEST-000002",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.manual,
        subtotal=Decimal("90"),
        discount=0,
        shipping=0,
        total=Decimal("90"),
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceItem(
            id="item-without-stock-ledger",
            invoice_id=invoice.id,
            product_id=product.id,
            sku=product.sku,
            description=product.name,
            quantity=Decimal("1"),
            unit_price=Decimal("90"),
            total=Decimal("90"),
        )
    )
    db.flush()

    result = overview(today, today, db, SimpleNamespace())
    assert result.unvalued_sales_items == 1
    assert result.gross_margin is None
    assert result.gross_margin_percent is None
