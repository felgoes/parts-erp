from decimal import Decimal

from app.core.security import encrypt_secret
from app.integrations.shopee import sync as sync_module
from app.models import InvoiceSource, MarketplaceAccount, SalesInvoice, Product
from sqlalchemy import select


class FakeShopeeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, params))
        for key, value in self.responses.items():
            if key in path:
                return value
        raise AssertionError(path)


def shopee_account(db):
    account = MarketplaceAccount(
        provider="shopee",
        seller_id="9001",
        encrypted_access_token=encrypt_secret("qa-only-test-token"),
        token_expires_at=None,
        active=True,
    )
    db.add(account)
    db.commit()
    return account


def test_shopee_order_creates_sales_invoice(db, monkeypatch):
    account = shopee_account(db)
    db.add(Product(sku="SH-1", name="Filtro", current_stock=Decimal(2)))
    db.commit()
    client = FakeShopeeClient(
        {
            "get_order_detail": {
                "order_list": [
                    {
                        "order_sn": "240101ABC",
                        "order_status": "READY_TO_SHIP",
                        "buyer_user_id": 42,
                        "item_list": [
                            {
                                "item_sku": "SH-1",
                                "item_name": "Filtro",
                                "quantity_purchased": 2,
                                "item_price": 15.5,
                            }
                        ],
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(sync_module, "client_for", lambda account: client)

    record = sync_module.sync_order(db, account, "240101ABC")

    invoice = db.scalar(select(SalesInvoice).where(SalesInvoice.id == record.invoice_id))
    assert invoice is not None
    assert invoice.source == InvoiceSource.shopee
    assert invoice.total == Decimal("31.00")
    assert invoice.marketplace_order_id == "shopee:240101ABC"


def test_shopee_product_import_is_idempotent(db, monkeypatch):
    account = shopee_account(db)
    client = FakeShopeeClient(
        {
            "get_item_list": {
                "item": [{"item_id": 1}],
                "next_cursor": "",
            },
            "get_item_base_info": {
                "item_list": [
                    {"item_id": 1, "item_sku": "SH-1", "item_name": "Filtro", "item_status": "NORMAL"}
                ]
            },
        }
    )
    monkeypatch.setattr(sync_module, "client_for", lambda account: client)

    assert sync_module.sync_products(db, account) == 1
    assert sync_module.sync_products(db, account) == 1
    assert db.scalar(select(Product).where(Product.sku == "SH-1")) is not None
    assert len(list(db.scalars(select(Product).where(Product.sku == "SH-1")))) == 1
