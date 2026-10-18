from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient
from app.integrations.mercadolivre.ml_fiscal import (  # noqa: F401
    automate_order_documents,
    issue_and_sync_invoice,
    retry_pending_automations,
    sync_invoice_documents,
)
from app.integrations.mercadolivre.ml_orders import (  # noqa: F401
    retry_due_orders,
    sync_order,
)
from app.integrations.mercadolivre.ml_products import (  # noqa: F401
    sync_product_stock,
    sync_products,
)
from app.integrations.mercadolivre.ml_shipping import (  # noqa: F401
    sync_seller_shipping_cost,
    sync_shipping_history,
    sync_shipping_label,
    sync_shipping_status,
)
from app.integrations.mercadolivre.ml_support import (  # noqa: F401
    FINISHED_FISCAL_STATUSES,
    FINISHED_LABEL_STATUSES,
    ORDER_RESOURCE,
    PRINTABLE_LOGISTICS,
    TERMINAL_SHIPPING_STATUSES,
    _account,
    _automation_config,
    _fiscal_entries,
    _parse_event_datetime,
    _resource_ids,
    _store_document,
    extract_invoice_order_ids,
    extract_sku,
    is_cancelled,
    is_paid,
    order_shipment_id,
)
from app.models import (  # noqa: F401  (reexportado para os testes)
    MarketplaceAccount,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    SalesInvoice,
)


def sync_all(db: Session, account: MarketplaceAccount) -> dict[str, int]:
    products = sync_products(db, account)
    orders = 0
    offset = 0
    synchronized_ids: set[str] = set()
    while True:
        result = MercadoLivreClient(db, account).get(
            f"/orders/search?seller={account.seller_id}&offset={offset}&limit=50"
        )
        ids = _resource_ids(result)
        if not ids:
            break
        for order_id in ids:
            sync_order(db, account.seller_id, f"/orders/{order_id}")
            synchronized_ids.add(order_id)
            orders += 1
        offset += len(ids)
        if len(ids) < 50:
            break
    # Retry known orders without an invoice as well. This backfills cancelled
    # orders already received by webhook before invoice generation was supported.
    missing_invoice_ids = list(
        db.scalars(
            select(MarketplaceOrder.external_order_id).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.seller_id == account.seller_id,
                MarketplaceOrder.invoice_id.is_(None),
            )
        )
    )
    for order_id in missing_invoice_ids:
        if order_id in synchronized_ids:
            continue
        sync_order(db, account.seller_id, f"/orders/{order_id}")
        orders += 1
    costs = reconcile_shipping_costs(db, account)
    return {"products": products, "orders": orders, "costs": costs}


def reconcile_shipping_costs(
    db: Session, account: MarketplaceAccount, limit: int = 25
) -> int:
    """Backfill seller shipping costs for recent imported sales."""
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.seller_id == account.seller_id,
                MarketplaceOrder.invoice_id.is_not(None),
            )
            .order_by(MarketplaceOrder.created_at.desc())
            .limit(max(limit * 4, limit))
        )
    )
    updated = 0
    for order in orders:
        payload = order.payload if isinstance(order.payload, dict) else {}
        if payload.get("_erp_shipping_cost_synced_at"):
            continue
        if sync_seller_shipping_cost(db, order, account) is not None:
            updated += 1
        db.commit()
        if updated >= limit:
            break
    return updated
