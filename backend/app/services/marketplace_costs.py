from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InvoiceSource, MarketplaceOrder, SalesInvoice

ZERO = Decimal("0")


@dataclass(frozen=True)
class MarketplaceOrderCosts:
    sale_fee: Decimal
    seller_shipping_cost: Decimal
    sale_fee_known: bool
    shipping_cost_known: bool

    @property
    def complete(self) -> bool:
        return self.sale_fee_known and self.shipping_cost_known


@dataclass(frozen=True)
class InvoiceRevenue:
    gross: Decimal
    marketplace_fee: Decimal
    seller_shipping: Decimal
    net: Decimal
    costs_complete: bool


@dataclass
class RevenueTotals:
    gross: Decimal = ZERO
    marketplace_fees: Decimal = ZERO
    seller_shipping: Decimal = ZERO
    net: Decimal = ZERO
    costs_pending: int = 0

    def add(self, revenue: InvoiceRevenue) -> None:
        self.gross += revenue.gross
        self.marketplace_fees += revenue.marketplace_fee
        self.seller_shipping += revenue.seller_shipping
        self.net += revenue.net
        if not revenue.costs_complete:
            self.costs_pending += 1


def _amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _sale_fee(payload: dict[str, Any]) -> tuple[Decimal, bool]:
    items = payload.get("order_items")
    if isinstance(items, list) and items:
        values = [_amount(item.get("sale_fee")) for item in items if isinstance(item, dict)]
        if len(values) == len(items) and all(value is not None for value in values):
            return sum((value for value in values if value is not None), ZERO), True

    # Alguns pedidos antigos não repetem sale_fee por item, mas trazem a
    # tarifa consolidada no pagamento. O valor já inclui custo fixo e parcelamento.
    payments = payload.get("payments")
    if isinstance(payments, list) and payments:
        values = [
            _amount(payment.get("marketplace_fee"))
            for payment in payments
            if isinstance(payment, dict)
        ]
        if values and all(value is not None for value in values):
            return sum((value for value in values if value is not None), ZERO), True
    return ZERO, False


def marketplace_order_costs(
    order: MarketplaceOrder, shipment_order_count: int = 1
) -> MarketplaceOrderCosts:
    payload = order.payload if isinstance(order.payload, dict) else {}
    sale_fee, sale_fee_known = _sale_fee(payload)
    shipment_cost = _amount(payload.get("_erp_seller_shipping_cost")) or ZERO
    shipping_cost = shipment_cost / Decimal(max(1, shipment_order_count))
    shipping_cost_known = bool(payload.get("_erp_shipping_cost_synced_at"))
    return MarketplaceOrderCosts(
        sale_fee=sale_fee,
        seller_shipping_cost=shipping_cost,
        sale_fee_known=sale_fee_known,
        shipping_cost_known=shipping_cost_known,
    )


def costs_for_invoices(
    db: Session, invoices: list[SalesInvoice]
) -> dict[str, MarketplaceOrderCosts]:
    invoice_ids = [invoice.id for invoice in invoices]
    if not invoice_ids:
        return {}
    orders = list(
        db.scalars(
            select(MarketplaceOrder).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.invoice_id.in_(invoice_ids),
            )
        )
    )
    shipment_ids = {order.shipment_id for order in orders if order.shipment_id}
    shipment_counts: dict[str, int] = {}
    if shipment_ids:
        shipment_orders = db.scalars(
            select(MarketplaceOrder).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.shipment_id.in_(shipment_ids),
            )
        )
        for order in shipment_orders:
            if order.shipment_id:
                shipment_counts[order.shipment_id] = (
                    shipment_counts.get(order.shipment_id, 0) + 1
                )
    return {
        str(order.invoice_id): marketplace_order_costs(
            order,
            shipment_counts.get(order.shipment_id or "", 1),
        )
        for order in orders
        if order.invoice_id
    }


def invoice_revenue(
    invoice: SalesInvoice, order_costs: MarketplaceOrderCosts | None
) -> InvoiceRevenue:
    gross = Decimal(invoice.total)
    if invoice.source != InvoiceSource.mercadolivre:
        return InvoiceRevenue(
            gross=gross,
            marketplace_fee=ZERO,
            seller_shipping=ZERO,
            net=gross,
            costs_complete=True,
        )
    if order_costs is None:
        return InvoiceRevenue(
            gross=gross,
            marketplace_fee=ZERO,
            seller_shipping=ZERO,
            net=gross,
            costs_complete=False,
        )
    fee = order_costs.sale_fee if order_costs.sale_fee_known else ZERO
    shipping = order_costs.seller_shipping_cost if order_costs.shipping_cost_known else ZERO
    return InvoiceRevenue(
        gross=gross,
        marketplace_fee=fee,
        seller_shipping=shipping,
        net=gross - fee - shipping,
        costs_complete=order_costs.complete,
    )


def revenue_by_invoice(
    db: Session, invoices: list[SalesInvoice]
) -> dict[str, InvoiceRevenue]:
    costs = costs_for_invoices(db, invoices)
    return {
        invoice.id: invoice_revenue(invoice, costs.get(invoice.id))
        for invoice in invoices
    }


def revenue_totals(revenues: list[InvoiceRevenue]) -> RevenueTotals:
    totals = RevenueTotals()
    for revenue in revenues:
        totals.add(revenue)
    return totals


def shipping_cost_synced_at(order: MarketplaceOrder) -> datetime | None:
    payload = order.payload if isinstance(order.payload, dict) else {}
    value = payload.get("_erp_shipping_cost_synced_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
