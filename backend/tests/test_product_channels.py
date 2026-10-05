from decimal import Decimal

import pytest

from app.integrations.mercadolivre import sync as ml_sync
from app.integrations.mercadolivre.client import MercadoLivreError
from app.models import MarketplaceAccount, Product, ProductMarketplaceListing
from app.schemas.common import ProductChannelDraftIn
from app.services.product_channels import save_channel_draft, sync_product_stock_all


def test_save_channel_draft_does_not_publish(db):
    product = Product(
        sku="PART-01", name="Peça teste", sale_price=Decimal("99.90"), current_stock=3
    )
    db.add(product)
    db.flush()

    listing = save_channel_draft(
        db,
        product,
        "mercadolivre",
        ProductChannelDraftIn(category_id="MLB123", title="Peça teste", price="99.90"),
    )

    assert listing.external_item_id is None
    assert listing.status == "draft"
    assert listing.sync_status == "draft"
    assert listing.channel_data["category_id"] == "MLB123"


def test_published_listing_cannot_change_category_from_draft(db):
    product = Product(sku="PART-02", name="Peça teste")
    listing = ProductMarketplaceListing(
        product=product,
        provider="mercadolivre",
        external_item_id="MLB999",
        category_id="MLB123",
        channel_data={"category_id": "MLB123"},
    )
    db.add(product)
    db.flush()

    with pytest.raises(ValueError, match="categoria.*não pode ser alterada"):
        save_channel_draft(
            db,
            product,
            "mercadolivre",
            ProductChannelDraftIn(category_id="MLB456"),
        )
    assert listing.category_id == "MLB123"


def test_draft_listing_is_never_sent_to_stock_sync(db, monkeypatch):
    product = Product(sku="PART-03", name="Peça teste", current_stock=Decimal("4"))
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="seller-1",
        encrypted_access_token="unused",  # noqa: S106 - fake value in a test fixture
        active=True,
    )
    listing = ProductMarketplaceListing(
        product=product,
        provider="mercadolivre",
        external_item_id=None,
        sync_status="draft",
    )
    db.add_all([product, account, listing])
    db.flush()
    calls = []
    monkeypatch.setattr(
        "app.integrations.mercadolivre.sync.sync_product_stock",
        lambda _db, _product: calls.append("sent"),
    )

    assert sync_product_stock_all(db, product) == {}
    assert calls == []


def test_ml_user_product_stock_uses_single_seller_warehouse_and_version(db, monkeypatch):
    product = Product(sku="PART-04", name="Peça teste", current_stock=Decimal("7"))
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="seller-2",
        encrypted_access_token="unused",  # noqa: S106 - fake value in a test fixture
        active=True,
    )
    listing = ProductMarketplaceListing(
        product=product,
        provider="mercadolivre",
        external_item_id="MLB123456",
        payload={"user_product_id": "MLBU123456"},
    )
    db.add_all([product, account, listing])
    db.flush()
    calls = []

    class FakeClient:
        def __init__(self, _db, _account):
            pass

        def get_with_headers(self, path):
            assert path == "/user-products/MLBU123456/stock"
            return {
                "locations": [
                    {
                        "type": "seller_warehouse",
                        "store_id": "store-1",
                        "network_node_id": "node-1",
                        "quantity": 12,
                    }
                ]
            }, {"x-version": "17"}

        def put(self, path, payload, extra_headers=None):
            calls.append((path, payload, extra_headers))
            return {}

    monkeypatch.setattr(ml_sync, "MercadoLivreClient", FakeClient)
    assert ml_sync.sync_product_stock(db, product) == 1
    assert calls == [
        (
            "/user-products/MLBU123456/stock/type/seller_warehouse",
            {"locations": [{"store_id": "store-1", "network_node_id": "node-1", "quantity": 7}]},
            {"x-version": "17"},
        )
    ]


def test_ml_user_product_with_multiple_warehouses_is_not_guessed(db, monkeypatch):
    product = Product(sku="PART-05", name="Peça teste", current_stock=Decimal("7"))
    account = MarketplaceAccount(
        provider="mercadolivre",
        seller_id="seller-3",
        encrypted_access_token="unused",  # noqa: S106 - fake value in a test fixture
        active=True,
    )
    listing = ProductMarketplaceListing(
        product=product,
        provider="mercadolivre",
        external_item_id="MLB654321",
        payload={"user_product_id": "MLBU654321"},
    )
    db.add_all([product, account, listing])
    db.flush()

    class FakeClient:
        def __init__(self, _db, _account):
            pass

        def get_with_headers(self, _path):
            return {
                "locations": [
                    {"type": "seller_warehouse", "store_id": "1", "network_node_id": "A"},
                    {"type": "seller_warehouse", "store_id": "2", "network_node_id": "B"},
                ]
            }, {"x-version": "4"}

    monkeypatch.setattr(ml_sync, "MercadoLivreClient", FakeClient)
    with pytest.raises(MercadoLivreError, match="vários depósitos"):
        ml_sync.sync_product_stock(db, product)
