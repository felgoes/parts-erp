from decimal import Decimal

from app.core.security import encrypt_secret
from app.integrations.mercadolivre import sync as sync_module
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.models import (
    InvoiceSource,
    MarketplaceAccount,
    MarketplaceOrder,
    SalesInvoice,
)
from app.services.marketplace_costs import invoice_revenue, marketplace_order_costs


def test_uses_order_sale_fee_and_seller_shipping_without_double_counting():
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="COST-1",
        seller_id="77",
        status="paid",
        payload={
            "order_items": [
                {"sale_fee": "4.50"},
                {"sale_fee": "5.50"},
            ],
            "_erp_seller_shipping_cost": "12.34",
            "_erp_shipping_cost_synced_at": "2026-10-18T18:00:00+00:00",
        },
    )
    invoice = SalesInvoice(
        number="VEN-COST-1",
        source=InvoiceSource.mercadolivre,
        total=Decimal("100.00"),
    )

    costs = marketplace_order_costs(order)
    revenue = invoice_revenue(invoice, costs)

    assert costs.sale_fee == Decimal("10.00")
    assert costs.seller_shipping_cost == Decimal("12.34")
    assert costs.complete is True
    assert revenue.net == Decimal("77.66")
    shared = marketplace_order_costs(order, shipment_order_count=2)
    assert shared.seller_shipping_cost == Decimal("6.17")


def test_marks_revenue_as_partial_when_shipping_cost_is_not_synced():
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="COST-2",
        seller_id="77",
        status="paid",
        payload={"order_items": [{"sale_fee": "8.00"}]},
    )
    invoice = SalesInvoice(
        number="VEN-COST-2",
        source=InvoiceSource.mercadolivre,
        total=Decimal("60.00"),
    )

    revenue = invoice_revenue(invoice, marketplace_order_costs(order))

    assert revenue.marketplace_fee == Decimal("8.00")
    assert revenue.seller_shipping == Decimal("0")
    assert revenue.net == Decimal("52.00")
    assert revenue.costs_complete is False


def test_falls_back_to_payment_marketplace_fee_for_old_orders():
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="COST-3",
        seller_id="77",
        status="paid",
        payload={
            "order_items": [{"quantity": 1, "unit_price": "40.00"}],
            "payments": [{"marketplace_fee": "6.25"}],
            "_erp_shipping_cost_synced_at": "2026-10-18T18:00:00+00:00",
        },
    )

    costs = marketplace_order_costs(order)

    assert costs.sale_fee == Decimal("6.25")
    assert costs.sale_fee_known is True


def test_seller_shipping_cost_uses_senders_not_receiver_cost(db, monkeypatch):
    account = MarketplaceAccount(
        seller_id="77",
        encrypted_access_token=encrypt_secret("token"),
        token_expires_at=None,
        active=True,
    )
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="SHIP-COST-1",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        shipment_id="555",
    )
    db.add_all([account, order])
    db.commit()
    monkeypatch.setattr(
        MercadoLivreClient,
        "get",
        lambda self, path, **kwargs: {
            "senders": [
                {"sender_id": 77, "cost": 18.5},
                {"sender_id": 99, "cost": 4},
            ],
            "receiver": {"cost": 0},
        },
    )

    cost = sync_module.sync_seller_shipping_cost(db, order, account)

    assert cost == Decimal("18.5")
    assert order.payload["_erp_seller_shipping_cost"] == "18.5"
    assert order.payload["_erp_shipping_cost_synced_at"]
