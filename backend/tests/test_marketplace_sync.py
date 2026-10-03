from decimal import Decimal
from types import SimpleNamespace

from app.core.security import encrypt_secret
from app.integrations.mercadolivre import sync as sync_module
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.models import InvoiceDocument, MarketplaceAccount, Product
from sqlalchemy import select


def marketplace_account(db):
    account = MarketplaceAccount(
        seller_id="77",
        encrypted_access_token=encrypt_secret("token"),
        token_expires_at=None,
        active=True,
    )
    db.add(account)
    db.flush()
    return account


def test_order_webhook_creates_invoice_and_documents(db, monkeypatch, tmp_path):
    account = marketplace_account(db)
    db.add(
        Product(
            sku="ABC-123",
            name="Pastilha",
            sale_price=Decimal("20"),
            current_stock=Decimal("5"),
        )
    )
    db.commit()
    order = {
        "id": 123,
        "seller": {"id": 77},
        "status": "paid",
        "buyer": {"id": 9, "first_name": "Ana", "last_name": "Silva"},
        "order_items": [
            {"item": {"seller_sku": "ABC-123"}, "quantity": 1, "unit_price": 20}
        ],
        "shipping": {"id": 555},
    }

    def fake_get(self, path):
        if path == "/orders/123":
            return order
        if path.startswith("/users/77/invoices/orders/123"):
            return [
                {
                    "id": "nf-1",
                    "status": "authorized",
                    "xml_location": "/nf.xml",
                    "danfe_location": "/nf.pdf",
                }
            ]
        raise AssertionError(path)

    downloads = []

    def fake_download(self, path):
        downloads.append(path)
        return ("content:" + path).encode()

    monkeypatch.setattr(MercadoLivreClient, "get", fake_get)
    monkeypatch.setattr(MercadoLivreClient, "download", fake_download)
    monkeypatch.setattr(
        sync_module,
        "get_settings",
        lambda: SimpleNamespace(documents_dir=str(tmp_path)),
    )

    record = sync_module.sync_order(db, "77", "/orders/123")

    assert record.invoice_id is not None
    docs = list(db.scalars(select(InvoiceDocument)))
    assert {doc.document_type for doc in docs} == {"xml", "pdf", "label"}
    assert "/shipment_labels?shipment_ids=555&response_type=pdf" in downloads
    assert len(downloads) == 3


def test_invoice_documents_are_idempotent(db, monkeypatch, tmp_path):
    account = marketplace_account(db)
    monkeypatch.setattr(
        sync_module,
        "get_settings",
        lambda: SimpleNamespace(documents_dir=str(tmp_path)),
    )
    calls = []

    def fake_get(self, path):
        return [
            {
                "id": "nf-1",
                "status": "authorized",
                "xml_location": "/nf.xml",
                "danfe_location": "/nf.pdf",
            }
        ]

    def fake_download(self, path):
        calls.append(path)
        return b"same"

    monkeypatch.setattr(MercadoLivreClient, "get", fake_get)
    monkeypatch.setattr(MercadoLivreClient, "download", fake_download)

    first = sync_module.sync_invoice_documents(db, account, "123", "invoice-1", {"shipping": {"id": 555}})
    second = sync_module.sync_invoice_documents(db, account, "123", "invoice-1", {"shipping": {"id": 555}})

    assert first == 3
    assert second == 0
    assert len(calls) == 3


def test_initial_sync_imports_products_and_orders(db, monkeypatch):
    account = marketplace_account(db)
    calls = []

    def fake_get(self, path):
        if "items/search" in path:
            return {"results": ["item-1"]}
        if path == "/items/item-1":
            return {
                "title": "Filtro",
                "seller_custom_field": "FLT-1",
                "price": 49.9,
                "available_quantity": 8,
                "status": "active",
            }
        if "orders/search" in path:
            return {"results": [{"id": "123"}]}
        raise AssertionError(path)

    def fake_order(db, seller_id, resource):
        calls.append((seller_id, resource))
        return None

    monkeypatch.setattr(MercadoLivreClient, "get", fake_get)
    monkeypatch.setattr(sync_module, "sync_order", fake_order)

    result = sync_module.sync_all(db, account)

    product = db.scalar(select(Product).where(Product.sku == "FLT-1"))
    assert result == {"products": 1, "orders": 1}
    assert product is not None
    assert product.current_stock == Decimal("8")
    assert calls == [("77", "/orders/123")]
