from datetime import UTC, date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import AdDailyMetric, MarketplaceAccount, Product, ProductMarketplaceListing

try:
    LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # Termux pode não ter o pacote tzdata.
    LOCAL_ZONE = timezone(timedelta(hours=-3), name="America/Sao_Paulo")


def _chunks(values: list[str], size: int = 20):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _metric_date(raw: object) -> date | None:
    if not isinstance(raw, str) or not raw:
        return None
    # The API returns daily buckets as ISO dates at 00:00Z. Preserve that
    # calendar label instead of shifting it to the previous Sao Paulo date.
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=LOCAL_ZONE)
            return parsed.astimezone(LOCAL_ZONE).date()
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
        for batch in _chunks(item_ids, size=1):
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
                    daily_visits = {}
                    for day in result.get("results", []):
                        if not isinstance(day, dict):
                            continue
                        metric_day = _metric_date(day.get("date"))
                        try:
                            visits = int(day["total"])
                        except (KeyError, TypeError, ValueError):
                            errors += 1
                            continue
                        if metric_day is None or visits < 0:
                            errors += 1
                            continue
                        daily_visits[metric_day] = daily_visits.get(metric_day, 0) + visits

                    # The API item total sums its daily buckets. Only when those totals
                    # reconcile can omitted dates inside the returned window be explicit zeroes.
                    try:
                        total_visits = int(result["total_visits"])
                        window_start = date.fromisoformat(str(result["date_from"])[:10])
                        window_end = date.fromisoformat(str(result["date_to"])[:10])
                    except (KeyError, TypeError, ValueError):
                        errors += 1
                    else:
                        if (
                            total_visits < 0
                            or window_end <= window_start
                            or sum(daily_visits.values()) != total_visits
                        ):
                            errors += 1
                        else:
                            for offset in range((window_end - window_start).days):
                                metric_day = window_start + timedelta(days=offset)
                                daily_visits.setdefault(metric_day, 0)

                    for metric_day, visits in daily_visits.items():
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
                        row.visits = visits
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


