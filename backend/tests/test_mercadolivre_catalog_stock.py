from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations.mercadolivre import ml_products
from app.models import MarketplaceAccount, MovementType, Product, ProductMarketplaceListing, StockMovement


def import_catalog(db, monkeypatch, details):
    account = MarketplaceAccount(seller_id="123", encrypted_access_token="test-only")
    db.add(account)
    db.commit()

    class CatalogClient:
        def __init__(self, db, account):
            pass

        def get(self, path):
            if path.startswith("/users/123/items/search?"):
                return {"results": list(details)}
            if path.startswith("/visits/") or path.endswith("/compatibilities?extended=true"):
                return {}
            return details[path.removeprefix("/items/")]

    monkeypatch.setattr(ml_products, "MercadoLivreClient", CatalogClient)
    return ml_products.sync_products(db, account)


@pytest.mark.parametrize("available,status", [(4, "active"), (0, "paused"), (8, "closed")])
def test_catalog_import_preserves_ledger_stock_including_full_transfers(db, monkeypatch, available, status):
    product = Product(sku="CATALOG-STOCK", name="Peça QA", current_stock=24, cost_price=Decimal("12.34"))
    db.add(product)
    db.flush()
    movement = StockMovement(
        product_id=product.id, movement_type=MovementType.adjustment,
        quantity=24, balance_after=24, unit_cost=Decimal("12.34"),
        movement_value=Decimal("296.16"), reason="QA opening balance",
        idempotency_key="qa-catalog-opening",
    )
    db.add(movement)
    db.commit()
    details = {
        "MLB123": {"id": "MLB123", "seller_sku": product.sku, "title": "Peça atualizada",
                   "price": 50, "available_quantity": available, "status": status,
                   "shipping": {"logistic_type": "fulfillment"}},
        "MLB456": {"id": "MLB456", "seller_sku": product.sku, "title": "Anúncio antigo",
                   "price": 50, "available_quantity": 11, "status": "closed"},
    }

    assert import_catalog(db, monkeypatch, details) == 2
    db.refresh(product)
    assert product.current_stock == Decimal("24")
    assert product.cost_price == Decimal("12.34")
    assert list(db.scalars(select(StockMovement))) == [movement]
    assert movement.quantity == product.current_stock
    listing = db.scalar(select(ProductMarketplaceListing).where(ProductMarketplaceListing.external_item_id == "MLB123"))
    assert listing.available_quantity == Decimal(available)
    assert listing.status == status


def test_new_catalog_product_does_not_create_unverified_inventory(db, monkeypatch):
    detail = {"id": "MLB789", "seller_sku": "NEW-CATALOG", "title": "Peça nova QA",
              "price": 50, "available_quantity": 9, "status": "active"}

    assert import_catalog(db, monkeypatch, {"MLB789": detail}) == 1
    product = db.scalar(select(Product).where(Product.sku == "NEW-CATALOG"))
    listing = db.scalar(select(ProductMarketplaceListing).where(ProductMarketplaceListing.product_id == product.id))
    assert product.current_stock == 0
    assert listing.available_quantity == 9
    assert list(db.scalars(select(StockMovement))) == []
