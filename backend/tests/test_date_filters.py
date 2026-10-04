from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.dashboard import financial_metrics, summary
from app.api.routes.invoices import list_invoices
from app.models import InvoiceSource, MarketplaceOrder, Product
from app.schemas.common import InvoiceCreate, InvoiceItemCreate
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice


def _sale(db: Session, product: Product, issued_at: datetime) -> None:
    invoice = create_invoice(
        db,
        InvoiceCreate(items=[InvoiceItemCreate(product_id=product.id, quantity=1)]),
    )
    confirm_invoice(db, invoice)
    invoice.issued_at = issued_at
    db.flush()


def test_invoice_and_dashboard_date_filters(db: Session) -> None:
    product = Product(
        sku="FILTER-001",
        name="Filtro de óleo",
        sale_price=Decimal("100.00"),
        cost_price=Decimal("50.00"),
        current_stock=Decimal("10"),
        minimum_stock=Decimal("1"),
    )
    db.add(product)
    db.flush()
    _sale(db, product, datetime(2026, 7, 15, 15, tzinfo=UTC))
    _sale(db, product, datetime(2026, 8, 15, 15, tzinfo=UTC))

    start, end = date(2026, 8, 1), date(2026, 8, 31)
    invoices = list_invoices(start, end, db, None)
    dashboard = summary(start, end, db, None)
    finance = financial_metrics(start, end, db, None)

    assert len(invoices) == 1
    assert dashboard.confirmed_sales == 1
    assert dashboard.revenue_month == Decimal("100.00")
    assert finance.sales_count == 1
    assert finance.revenue == Decimal("100.00")
    assert finance.previous_revenue == Decimal("100.00")
    assert len(finance.daily) == 31


def test_cancelled_marketplace_sale_stays_visible_but_is_not_revenue(db: Session) -> None:
    product = Product(
        sku="RETURN-001",
        name="Peça devolvida",
        sale_price=Decimal("125.00"),
        cost_price=Decimal("60.00"),
        current_stock=Decimal("4"),
        minimum_stock=Decimal("1"),
    )
    db.add(product)
    db.flush()
    invoice = create_invoice(
        db,
        InvoiceCreate(items=[InvoiceItemCreate(product_id=product.id, quantity=1)]),
        source=InvoiceSource.mercadolivre,
        marketplace_order_id="987654",
    )
    confirm_invoice(db, invoice)
    invoice.issued_at = datetime(2026, 8, 15, 15, tzinfo=UTC)
    cancel_invoice(db, invoice)
    product.current_stock = Decimal("4")
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="987654",
        seller_id="77",
        status="cancelled",
        invoice_id=invoice.id,
        payload={
            "cancel_detail": {"description": "Devolução solicitada pelo comprador"},
            "payments": [{"status": "refunded"}],
        },
    )
    db.add(order)
    db.flush()

    start, end = date(2026, 8, 1), date(2026, 8, 31)
    invoices = list_invoices(start, end, db, None)
    dashboard = summary(start, end, db, None)
    finance = financial_metrics(start, end, db, None)

    assert len(invoices) == 1
    assert invoices[0].status == "cancelled"
    assert invoices[0].after_sale is not None
    assert invoices[0].after_sale.reason == "Devolução solicitada pelo comprador"
    assert invoices[0].after_sale.payment_status == "refunded"
    assert invoices[0].after_sale.refund_amount == Decimal("125.00")
    assert dashboard.recent_invoices[0].status == "cancelled"
    assert dashboard.confirmed_sales == 0
    assert dashboard.cancelled_sales == 1
    assert dashboard.cancelled_amount == Decimal("125.00")
    assert dashboard.revenue_month == Decimal("0")
    assert finance.sales_count == 0
    assert finance.revenue == Decimal("0")
    assert finance.cancelled_count == 1
    assert finance.cancelled_amount == Decimal("125.00")


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 8, 2), date(2026, 8, 1)), (date(2025, 1, 1), date(2026, 1, 1))],
)
def test_invoice_filter_rejects_invalid_or_oversized_range(
    db: Session, start: date, end: date
) -> None:
    with pytest.raises(HTTPException) as exc:
        list_invoices(start, end, db, None)
    assert exc.value.status_code == 422
