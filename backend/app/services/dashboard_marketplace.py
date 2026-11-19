from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.periods import BRAZIL_TZ as TZ
from app.integrations.mercadolivre.ml_support import is_cancelled, is_paid
from app.models import (
    AdDailyMetric,
    InvoiceStatus,
    MarketplaceAccount,
    MarketplaceDashboardSync,
    MarketplaceOrder,
    Product,
    ProductMarketplaceListing,
    SalesInvoice,
)


def _bounds(start: date, end: date):
    return (
        datetime.combine(start, time.min, TZ).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, TZ).astimezone(UTC),
    )


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _known_orders(db, accounts, start, end):
    lower, upper = _bounds(start, end)
    orders = list(
        db.scalars(
            select(MarketplaceOrder).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.seller_id.in_([a.seller_id for a in accounts]),
                MarketplaceOrder.created_at >= lower,
                MarketplaceOrder.created_at < upper,
            )
        )
    )
    eligible = []
    for order in orders:
        payload = order.payload if isinstance(order.payload, dict) else {}
        if is_cancelled(payload) or not is_paid(payload):
            continue
        if order.invoice_id:
            invoice = db.get(SalesInvoice, order.invoice_id)
            if invoice and invoice.status == InvoiceStatus.cancelled:
                continue
        created = (
            order.created_at.replace(tzinfo=UTC)
            if order.created_at.tzinfo is None
            else order.created_at
        )
        if start <= created.astimezone(TZ).date() <= end:
            eligible.append(order)
    return orders, eligible


def dashboard_marketplace_metrics(db: Session, start: date, end: date):
    accounts = list(
        db.scalars(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "mercadolivre", MarketplaceAccount.active.is_(True)
            )
        )
    )
    base = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "connected": bool(accounts),
    }
    if not accounts:
        return {
            **base,
            "sync_state": "disconnected",
            "partial": False,
            "last_synced_at": None,
            "metrics": {
                k: {"value": None, "state": "unavailable"}
                for k in ("orders", "units", "gross", "average_ticket", "visits", "conversion")
            },
            "products_state": "unavailable",
            "products": [],
        }
    states = list(
        db.scalars(
            select(MarketplaceDashboardSync).where(
                MarketplaceDashboardSync.account_id.in_([a.id for a in accounts]),
                MarketplaceDashboardSync.period_start == start,
                MarketplaceDashboardSync.period_end == end,
            )
        )
    )
    order_complete = len(states) == len(accounts) and all(
        s.sync_status == "succeeded" and not s.partial for s in states
    )
    all_orders, orders = _known_orders(db, accounts, start, end)
    order_partial = not order_complete or any(
        o.sync_status in {"error", "pending"} for o in all_orders
    )
    order_ids = {o.external_order_id for o in orders}
    count = len(order_ids) if order_complete or orders else None
    units = Decimal("0")
    gross = Decimal("0")
    units_bad = gross_bad = False
    any_valid_price = False
    ranks = {}
    order_item_pairs = set()
    for order in orders:
        payload = order.payload if isinstance(order.payload, dict) else {}
        lines = payload.get("order_items")
        if not isinstance(lines, list) or not lines:
            units_bad = gross_bad = True
            continue
        for line in lines:
            if not isinstance(line, dict):
                units_bad = gross_bad = True
                continue
            item = line.get("item") if isinstance(line.get("item"), dict) else {}
            item_id = str(item.get("id") or "")
            variation = str(item.get("variation_id") or "")
            if item_id:
                order_item_pairs.add((order.seller_id, item_id))
            else:
                units_bad = True
            qty = _number(line.get("quantity"))
            if qty is None or qty < 0:
                units_bad = True
                continue
            units += qty
            price = _number(line.get("unit_price"))
            currency = str(line.get("currency_id") or payload.get("currency_id") or "")
            if price is None or currency != "BRL":
                gross_bad = True
            else:
                gross += qty * price
                any_valid_price = True
            if item_id:
                key = f"{order.seller_id}:{item_id}:{variation}"
                entry = ranks.setdefault(
                    key,
                    {
                        "key": key,
                        "item_id": item_id,
                        "variation_id": variation,
                        "name": item.get("title") or f"Anúncio {item_id}",
                        "sku": item.get("seller_sku") or item.get("seller_custom_field") or "",
                        "units": Decimal("0"),
                        "pending_link": True,
                        "product_id": None,
                    },
                )
                entry["units"] += qty

    listings = db.execute(
        select(ProductMarketplaceListing, Product)
        .join(Product, Product.id == ProductMarketplaceListing.product_id)
        .where(
            ProductMarketplaceListing.provider == "mercadolivre",
            ProductMarketplaceListing.external_item_id.is_not(None),
        )
    ).all()
    by_pair = {}
    account_ids = {a.seller_id: a.id for a in accounts}
    listing_items = defaultdict(dict)
    unknown_listing = False
    for listing, product in listings:
        data = listing.payload if isinstance(listing.payload, dict) else {}
        seller = str(data.get("seller_id") or "")
        if not seller and len(accounts) == 1:
            seller = accounts[0].seller_id
        if seller in account_ids and listing.external_item_id:
            listing_items[seller][str(listing.external_item_id)] = listing
            by_pair[(seller, str(listing.external_item_id))] = (listing, product)
        elif not seller:
            unknown_listing = True
    for entry in ranks.values():
        listing_product = by_pair.get((entry["key"].split(":", 1)[0], entry["item_id"]))
        if listing_product:
            listing, product = listing_product
            entry.update(
                {
                    "key": f"product:{product.id}",
                    "product_id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "pending_link": False,
                }
            )
    merged = {}
    for row in ranks.values():
        entry = merged.setdefault(row["key"], {**row, "units": Decimal("0")})
        entry["units"] += row["units"]
    products = sorted(
        merged.values(), key=lambda r: (-r["units"], str(r["sku"]).casefold(), r["key"])
    )[:5]
    for i, row in enumerate(products, 1):
        row["rank"] = i
        row["units"] = str(row["units"])

    rows = list(
        db.scalars(
            select(AdDailyMetric).where(
                AdDailyMetric.channel == "mercadolivre",
                AdDailyMetric.account_id.in_([a.id for a in accounts]),
                AdDailyMetric.metric_date >= start,
                AdDailyMetric.metric_date <= end,
            )
        )
    )
    metric = {(r.account_id, r.item_id, r.metric_date): r for r in rows}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    visits = 0
    visits_known = False
    visits_partial = unknown_listing
    visit_last = []
    compatible = all(pair in by_pair for pair in order_item_pairs)
    for account in accounts:
        item_listings = listing_items.get(account.seller_id, {})
        if not item_listings:
            visits_partial = True
            continue
        family_days = defaultdict(list)
        complete = True
        synced = []
        for item_id, listing in item_listings.items():
            family = listing.parent_item_id or item_id
            for day in days:
                row = metric.get((account.id, item_id, day))
                if not row or row.visits is None or row.sync_status != "ok":
                    complete = False
                    visits_partial = True
                    continue
                family_days[(family, day)].append(row.visits)
                visits_known = True
                synced.append(row.synced_at)
        for values in family_days.values():
            visits += max(values) if len(values) > 1 and len(set(values)) == 1 else sum(values)
        if complete and synced:
            visit_last.append(min(synced))
    visit_state = "partial" if visits_partial else ("ok" if visits_known else "unavailable")
    visit_value = visits if visits_known else None
    units_value = units if orders or order_complete else None
    gross_value = gross if any_valid_price or (order_complete and not orders) else None
    units_state = (
        "partial"
        if order_partial or units_bad
        else ("ok" if units_value is not None else "unavailable")
    )
    gross_state = (
        "partial"
        if order_partial or gross_bad
        else ("ok" if gross_value is not None else "unavailable")
    )
    ticket = (
        (gross / count).quantize(Decimal("0.01"))
        if count and not order_partial and not gross_bad
        else None
    )
    conversion = (
        (Decimal(count) / Decimal(visits) * 100).quantize(Decimal("0.01"))
        if (
            order_complete
            and not order_partial
            and visit_state == "ok"
            and compatible
            and count is not None
            and visits_known
            and visits > 0
        )
        else None
    )
    sync_state = (
        "updating"
        if any(s.sync_status in {"pending", "running"} for s in states)
        else "failed"
        if any(s.sync_status == "failed" for s in states)
        else "complete"
        if order_complete and visit_state == "ok"
        else "partial"
    )
    latest_orders = [s.last_success_at for s in states if s.last_success_at]
    last_synced = (
        min(min(latest_orders), min(visit_last))
        if latest_orders and len(visit_last) == len(accounts)
        else None
    )

    def m(value, state, note=None):
        return {"value": value, "state": state, "note": note}

    return {
        **base,
        "sync_state": sync_state,
        "partial": order_partial or units_bad or gross_bad or visit_state != "ok",
        "last_synced_at": last_synced,
        "metrics": {
            "orders": m(
                count,
                "partial"
                if order_partial and count is not None
                else ("unavailable" if count is None else "ok"),
                "Pedidos do período incompletos" if order_partial else None,
            ),
            "units": m(
                units_value,
                units_state,
                "Pedidos incompletos"
                if order_partial
                else ("Linhas sem quantidade confiável" if units_bad else None),
            ),
            "gross": m(
                str(gross_value) if gross_value is not None else None,
                gross_state,
                "Pedidos incompletos"
                if order_partial
                else ("Preço ou moeda ausente em uma linha" if gross_bad else None),
            ),
            "average_ticket": m(
                str(ticket) if ticket is not None else None,
                "ok" if ticket is not None else "unavailable",
            ),
            "visits": m(
                visit_value,
                visit_state,
                "Cobertura incompleta" if visit_state == "partial" else None,
            ),
            "conversion": m(
                str(conversion) if conversion is not None else None,
                "ok" if conversion is not None else "unavailable",
                "Exige cobertura compatível e visitas positivas" if conversion is None else None,
            ),
        },
        "products": products,
        "products_state": "partial"
        if order_partial or units_bad
        else ("empty" if order_complete and not products else "complete"),
    }
