from datetime import date

from app.models import AdDailyMetric, MarketplaceAccount, Product, ProductMarketplaceListing
from app.services.ad_performance import _metric_date, sync_ad_metrics_for_account


def test_daily_marketplace_date_keeps_api_calendar_bucket():
    assert _metric_date("2026-11-19T00:00:00Z") == date(2026, 11, 19)


def test_daily_marketplace_date_accepts_plain_iso_date():
    assert _metric_date("2026-11-19") == date(2026, 11, 19)


def test_daily_marketplace_date_rejects_invalid_value():
    assert _metric_date("not-a-date") is None


def test_sync_ad_metrics_queries_one_item_per_request(db, monkeypatch):
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-visits",
        active=True,
        encrypted_access_token="fake-token",
    )
    db.add(account)
    db.flush()
    item_ids = ["ITEM-ONE", "ITEM-TWO"]
    for index, item_id in enumerate(item_ids):
        product = Product(
            sku=f"SKU-{index}",
            name=f"Product {index}",
            sale_price=10,
            cost_price=5,
            current_stock=1,
            minimum_stock=0,
        )
        db.add(product)
        db.flush()
        db.add(
            ProductMarketplaceListing(
                product_id=product.id,
                provider="mercadolivre",
                external_item_id=item_id,
                payload={"seller_id": account.seller_id},
            )
        )
    db.flush()
    requests = []

    class Client:
        def __init__(self, *_args):
            pass

        def get(self, path):
            from urllib.parse import parse_qs, urlparse

            requested = parse_qs(urlparse(path).query)["ids"][0].split(",")
            requests.append(requested)
            assert len(requested) == 1
            return [
                {
                    "item_id": requested[0],
                    "total_visits": 15,
                    "date_from": "2026-11-18T00:00:00Z",
                    "date_to": "2026-11-21T00:00:00Z",
                    "results": [{"date": "2026-11-19T00:00:00Z", "total": 15}],
                }
            ]

    monkeypatch.setattr("app.services.ad_metrics_sync.MercadoLivreClient", Client)
    result = sync_ad_metrics_for_account(db, account.id)
    assert result == {"updated": 6, "errors": 0}
    assert requests == [[item_id] for item_id in item_ids]
    rows = list(db.query(AdDailyMetric).filter_by(account_id=account.id))
    assert len(rows) == 6
    assert {
        item_id: {
            row.metric_date.isoformat(): row.visits
            for row in rows
            if row.item_id == item_id
        }
        for item_id in item_ids
    } == {
        "ITEM-ONE": {"2026-11-18": 0, "2026-11-19": 15, "2026-11-20": 0},
        "ITEM-TWO": {"2026-11-18": 0, "2026-11-19": 15, "2026-11-20": 0},
    }


def test_sync_ad_metrics_records_confirmed_zero_visits(db, monkeypatch):
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="qa-zero-visits",
        active=True,
        encrypted_access_token="fake-token",
    )
    db.add(account)
    db.flush()
    product = Product(
        sku="ZERO",
        name="No visits",
        sale_price=10,
        cost_price=5,
        current_stock=1,
        minimum_stock=0,
    )
    db.add(product)
    db.flush()
    db.add(
        ProductMarketplaceListing(
            product_id=product.id,
            provider="mercadolivre",
            external_item_id="ITEM-ZERO",
            payload={"seller_id": account.seller_id},
        )
    )
    db.flush()

    class Client:
        def __init__(self, *_args):
            pass

        def get(self, _path):
            return [{
                "item_id": "ITEM-ZERO",
                "total_visits": 0,
                "date_from": "2026-11-18T00:00:00Z",
                "date_to": "2026-11-21T00:00:00Z",
                "results": [],
            }]

    monkeypatch.setattr("app.services.ad_metrics_sync.MercadoLivreClient", Client)
    result = sync_ad_metrics_for_account(db, account.id)
    rows = list(db.query(AdDailyMetric).filter_by(account_id=account.id))
    assert result == {"updated": 3, "errors": 0}
    assert {row.metric_date.isoformat(): row.visits for row in rows} == {
        "2026-11-18": 0,
        "2026-11-19": 0,
        "2026-11-20": 0,
    }
