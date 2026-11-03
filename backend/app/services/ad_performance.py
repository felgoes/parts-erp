from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.ml_support import is_cancelled, is_paid
from app.models import (
    AdDailyMetric,
    MarketplaceAccount,
    MarketplaceOrder,
    Product,
    ProductMarketplaceListing,
)

LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")


def _chunks(values: list[str], size: int = 20):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _metric_date(raw: object) -> date | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_ZONE)
        return parsed.astimezone(LOCAL_ZONE).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def sync_ad_metrics_for_account(db: Session, account_id: str) -> dict[str, int]:
    account = db.get(MarketplaceAccount, account_id)
    if not account or not account.active or account.provider != "mercadolivre":
        return {"updated": 0, "errors": 0}
    accounts = list(
        db.scalars(
            select(MarketplaceAccount).where(
                MarketplaceAccount.active.is_(True), MarketplaceAccount.provider == "mercadolivre"
            )
        )
    )
    listings = list(
        db.execute(
            select(ProductMarketplaceListing, Product)
            .join(Product, Product.id == ProductMarketplaceListing.product_id)
            .where(ProductMarketplaceListing.provider == "mercadolivre")
            .where(ProductMarketplaceListing.external_item_id.is_not(None))
        ).all()
    )
    by_item = {}
    for listing, product in listings:
        payload = listing.payload if isinstance(listing.payload, dict) else {}
        seller_id = str(payload.get("seller_id") or "")
        if seller_id and seller_id != account.seller_id:
            continue
        if not seller_id and len(accounts) > 1:
            continue
        if listing.external_item_id:
            by_item[str(listing.external_item_id)] = (listing, product)
    if not by_item:
        return {"updated": 0, "errors": 0}

    known_items = set(
        db.scalars(
            select(AdDailyMetric.item_id).where(AdDailyMetric.account_id == account.id).distinct()
        )
    )
    groups = {
        8: [item for item in by_item if item in known_items],
        150: [item for item in by_item if item not in known_items],
    }
    client = MercadoLivreClient(db, account)
    synced_at = datetime.now(UTC)
    updated = errors = 0
    for lookback, item_ids in groups.items():
        for batch in _chunks(item_ids):
            ids = quote(",".join(batch), safe=",")
            try:
                response = client.get(
                    f"/items/visits/time_window?ids={ids}&last={lookback}&unit=day"
                )
                if not isinstance(response, list):
                    raise MercadoLivreError("Resposta de visitas inválida")
                returned = {
                    str(row.get("item_id")): row for row in response if isinstance(row, dict)
                }
                for item_id in batch:
                    result = returned.get(item_id)
                    if result is None:
                        errors += 1
                        continue
                    listing, _product = by_item[item_id]
                    parent_id = listing.parent_item_id or None
                    for day in result.get("results", []):
                        if not isinstance(day, dict):
                            continue
                        metric_day = _metric_date(day.get("date"))
                        if metric_day is None or "total" not in day:
                            continue
                        row = db.scalar(
                            select(AdDailyMetric).where(
                                AdDailyMetric.account_id == account.id,
                                AdDailyMetric.channel == "mercadolivre",
                                AdDailyMetric.item_id == item_id,
                                AdDailyMetric.metric_date == metric_day,
                            )
                        )
                        if row is None:
                            row = AdDailyMetric(
                                account_id=account.id,
                                channel="mercadolivre",
                                item_id=item_id,
                                metric_date=metric_day,
                            )
                            db.add(row)
                        row.parent_item_id = parent_id
                        row.visits = int(day["total"])
                        row.source_updated_at = None
                        row.synced_at = synced_at
                        row.sync_status = "ok"
                        updated += 1
                db.commit()
            except MercadoLivreError as exc:
                db.rollback()
                errors += len(batch)
                if exc.status_code in {429, 500, 502, 503, 504}:
                    raise
            except Exception:
                db.rollback()
                raise
    return {"updated": updated, "errors": errors}


def _order_metrics(
    db: Session, start: date, end: date, seller_ids: set[str]
) -> dict[tuple[str, date], set[str]]:
    if not seller_ids:
        return {}
    start_at = datetime.combine(start, datetime.min.time(), LOCAL_ZONE).astimezone(UTC)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), LOCAL_ZONE).astimezone(
        UTC
    )
    orders = db.scalars(
        select(MarketplaceOrder).where(
            MarketplaceOrder.provider == "mercadolivre",
            MarketplaceOrder.seller_id.in_(seller_ids),
            MarketplaceOrder.created_at >= start_at,
            MarketplaceOrder.created_at < end_at,
        )
    )
    result: dict[tuple[str, date], set[str]] = defaultdict(set)
    for order in orders:
        payload = order.payload if isinstance(order.payload, dict) else {}
        payments = payload.get("payments") or []
        if is_cancelled(payload) or (payments and not is_paid(payload)):
            continue
        if not payments and str(payload.get("status") or "").lower() not in {"paid", "confirmed"}:
            continue
        created = order.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        local_day = created.astimezone(LOCAL_ZONE).date()
        if not start <= local_day <= end:
            continue
        for line in payload.get("order_items", []):
            item = line.get("item") if isinstance(line, dict) else None
            item_id = str(item.get("id") or "") if isinstance(item, dict) else ""
            if item_id:
                result[(item_id, local_day)].add(order.external_order_id)
    return result


def ad_performance_summary(
    db: Session,
    *,
    start: date,
    end: date,
    channel: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "visits",
    sort_direction: str = "desc",
) -> dict:
    accounts = list(
        db.scalars(select(MarketplaceAccount).where(MarketplaceAccount.provider == "mercadolivre"))
    )
    account_by_seller = {account.seller_id: account for account in accounts}
    listings = db.execute(
        select(ProductMarketplaceListing, Product)
        .join(Product, Product.id == ProductMarketplaceListing.product_id)
        .where(ProductMarketplaceListing.provider == "mercadolivre")
        .where(ProductMarketplaceListing.external_item_id.is_not(None))
    ).all()
    needle = (search or "").strip().casefold()
    ads = []
    for listing, product in listings:
        payload = listing.payload if isinstance(listing.payload, dict) else {}
        seller_id = str(payload.get("seller_id") or "")
        account = (
            account_by_seller.get(seller_id)
            if seller_id
            else (accounts[0] if len(accounts) == 1 else None)
        )
        if account is None:
            continue
        if channel and channel != listing.provider:
            continue
        raw_status = (listing.status or "").lower()
        status_label = raw_status if raw_status in {"active", "paused", "closed"} else "unavailable"
        if status and status != status_label:
            continue
        if (
            needle
            and needle
            not in " ".join(
                [listing.title or product.name, product.sku, listing.external_item_id or ""]
            ).casefold()
        ):
            continue
        ads.append((listing, product, account))

    item_ids = {str(listing.external_item_id) for listing, _product, _account in ads}
    account_ids = {account.id for _listing, _product, account in ads}
    metric_rows = list(
        db.scalars(
            select(AdDailyMetric).where(
                AdDailyMetric.account_id.in_(account_ids or {""}),
                AdDailyMetric.item_id.in_(item_ids or {""}),
                AdDailyMetric.channel == "mercadolivre",
                AdDailyMetric.metric_date >= start,
                AdDailyMetric.metric_date <= end,
            )
        )
    )
    metrics_by_key = {(row.account_id, row.item_id, row.metric_date): row for row in metric_rows}
    seller_ids = {account.seller_id for _listing, _product, account in ads}
    order_counts = {
        key: value
        for key, value in _order_metrics(db, start, end, seller_ids).items()
        if key[0] in item_ids
    }
    records = []
    for listing, product, account in ads:
        item_id = str(listing.external_item_id)
        daily = []
        item_metrics = [
            metrics_by_key.get((account.id, item_id, start + timedelta(days=i)))
            for i in range((end - start).days + 1)
        ]
        known_visits = [row.visits for row in item_metrics if row and row.visits is not None]
        visits = sum(known_visits) if known_visits else None
        orders = len(
            set().union(
                *(
                    order_counts.get((item_id, start + timedelta(days=i)), set())
                    for i in range((end - start).days + 1)
                )
            )
        )
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            metric = metrics_by_key.get((account.id, item_id, day))
            day_orders = len(order_counts.get((item_id, day), set()))
            day_visits = metric.visits if metric else None
            daily.append(
                {
                    "date": day,
                    "visits": day_visits,
                    "orders": day_orders,
                    "conversion": day_orders / day_visits * 100 if day_visits else None,
                    "sync_status": metric.sync_status if metric else "partial",
                }
            )
        updated = max((row.synced_at for row in item_metrics if row), default=None)
        records.append(
            {
                "channel": listing.provider,
                "item_id": item_id,
                "parent_item_id": listing.parent_item_id,
                "sku": product.sku,
                "title": listing.title or product.name,
                "thumbnail": listing.thumbnail,
                "status": status_label,
                "visits": visits,
                "orders": orders,
                "conversion": orders / visits * 100 if visits else None,
                "updated_at": updated,
                "daily": daily,
            }
        )
    if sort_by in {"visits", "orders", "conversion"}:
        present = [row for row in records if row[sort_by] is not None]
        missing = [row for row in records if row[sort_by] is None]
        present.sort(key=lambda row: row[sort_by], reverse=sort_direction == "desc")
        records = present + missing
    elif sort_by in {"title", "status"}:
        records.sort(key=lambda row: row[sort_by].casefold(), reverse=sort_direction == "desc")
    total_ads = len(records)
    all_orders = (
        set().union(*(values for values in order_counts.values())) if order_counts else set()
    )
    family_daily: dict[tuple[str, date], list[int]] = defaultdict(list)
    for metric in metric_rows:
        family_daily[(metric.parent_item_id or metric.item_id, metric.metric_date)].append(
            metric.visits or 0
        )
    unique_visits = sum(max(values) for values in family_daily.values())
    daily_summary = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        values = [
            values for (_root, metric_day), values in family_daily.items() if metric_day == day
        ]
        day_visits = sum(max(group) for group in values) if values else None
        day_orders = set().union(
            *(ids for (item, metric_day), ids in order_counts.items() if metric_day == day)
        )
        daily_summary.append(
            {
                "date": day,
                "visits": day_visits,
                "orders": len(day_orders),
                "conversion": len(day_orders) / day_visits * 100 if day_visits else None,
            }
        )
    expected_days = (end - start).days + 1
    missing_days = any(
        sum(1 for row in item_metrics if row and row.visits is not None) < expected_days
        for item_metrics in (
            [
                metrics_by_key.get(
                    (account.id, str(listing.external_item_id), start + timedelta(days=i))
                )
                for i in range(expected_days)
            ]
            for listing, _product, account in ads
        )
    )
    last_synced = db.scalar(
        select(func.max(AdDailyMetric.synced_at)).where(
            AdDailyMetric.account_id.in_({account.id for account in accounts} or {""})
        )
    )
    page_start = (page - 1) * page_size
    return {
        "start_date": start,
        "end_date": end,
        "generated_at": datetime.now(UTC),
        "last_synced_at": last_synced,
        "connected": any(account.active for account in accounts),
        "total_ads": total_ads,
        "totals": {
            "visits": unique_visits if metric_rows else None,
            "orders": len(all_orders),
            "conversion": len(all_orders) / unique_visits * 100 if unique_visits else None,
            "ads_with_data": len({row.item_id for row in metric_rows}),
        },
        "daily": daily_summary,
        "partial": missing_days
        or any(row.sync_status != "ok" for row in metric_rows)
        or len({row.item_id for row in metric_rows}) < len(ads),
        "ads": records[page_start : page_start + page_size],
    }
