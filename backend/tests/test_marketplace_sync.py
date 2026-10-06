from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.api.routes.integrations import request_order_fiscal_document
from app.core.config import Settings
from app.core.security import encrypt_secret
from app.integrations.mercadolivre import sync as sync_module
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceOrder,
    Product,
    SalesInvoice,
)


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


def test_label_format_is_configured_as_pdf_by_default():
    assert Settings().mercadolivre_label_format == "pdf"


def test_order_webhook_creates_invoice_and_documents(db, monkeypatch, tmp_path):
    marketplace_account(db)
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
        "order_items": [{"item": {"seller_sku": "ABC-123"}, "quantity": 1, "unit_price": 20}],
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
        lambda: SimpleNamespace(
            documents_dir=str(tmp_path),
            mercadolivre_auto_issue_invoice=False,
            mercadolivre_auto_download_label=False,
        ),
    )

    record = sync_module.sync_order(db, "77", "/orders/123")

    assert record.invoice_id is not None
    docs = list(db.scalars(select(InvoiceDocument)))
    assert {doc.document_type for doc in docs} == {"xml", "pdf"}
    assert len(downloads) == 2


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

    first = sync_module.sync_invoice_documents(
        db, account, "123", "invoice-1", {"shipping": {"id": 555}}
    )
    second = sync_module.sync_invoice_documents(
        db, account, "123", "invoice-1", {"shipping": {"id": 555}}
    )

    assert first == 2
    assert second == 0
    assert len(calls) == 2


def test_manual_invoice_request_works_when_automatic_issuance_is_disabled(db, monkeypatch):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-TEST-001", marketplace_order_id="123")
    order = MarketplaceOrder(
        external_order_id="123",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
    )
    db.add(order)
    db.commit()
    calls = []

    monkeypatch.setattr(
        sync_module,
        "_automation_config",
        lambda _db: SimpleNamespace(auto_issue_invoice=False),
    )
    monkeypatch.setattr(MercadoLivreClient, "get", lambda _self, _path: [])

    def fake_post(_self, path, payload):
        calls.append((path, payload))
        return [{"id": "nf-manual-1", "status": "pending"}]

    monkeypatch.setattr(MercadoLivreClient, "post", fake_post)

    sync_module.issue_and_sync_invoice(db, order, account, force_issue=True)
    assert calls == [
        ("/users/77/invoices/orders", {"orders": [123]}),
    ]
    assert order.external_invoice_id == "nf-manual-1"

    # Even if the follow-up lookup is briefly empty, don't issue a duplicate.
    sync_module.issue_and_sync_invoice(db, order, account, force_issue=True)
    assert len(calls) == 1


def test_manual_invoice_request_treats_missing_invoice_as_not_yet_issued(db, monkeypatch):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-TEST-404", marketplace_order_id="124")
    order = MarketplaceOrder(
        external_order_id="124",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
    )
    db.add(order)
    db.commit()
    calls = []

    monkeypatch.setattr(
        sync_module,
        "_automation_config",
        lambda _db: SimpleNamespace(auto_issue_invoice=False),
    )

    def fake_get(_self, path):
        assert path == "/users/77/invoices/orders/124"
        raise MercadoLivreError("Mercado Livre respondeu 404: invoice not found", status_code=404)

    def fake_post(_self, path, payload):
        calls.append((path, payload))
        return [{"id": "nf-manual-404", "status": "pending"}]

    monkeypatch.setattr(MercadoLivreClient, "get", fake_get)
    monkeypatch.setattr(MercadoLivreClient, "post", fake_post)

    sync_module.issue_and_sync_invoice(db, order, account, force_issue=True)

    assert calls == [("/users/77/invoices/orders", {"orders": [124]})]
    assert order.external_invoice_id == "nf-manual-404"
    assert order.fiscal_status == "pending"
    assert order.fiscal_error is None


def test_manual_invoice_request_does_not_issue_after_non_404_lookup_error(db, monkeypatch):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-TEST-500", marketplace_order_id="125")
    order = MarketplaceOrder(
        external_order_id="125",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
    )
    db.add(order)
    db.commit()
    posts = []

    monkeypatch.setattr(
        sync_module,
        "_automation_config",
        lambda _db: SimpleNamespace(auto_issue_invoice=False),
    )
    monkeypatch.setattr(
        MercadoLivreClient,
        "get",
        lambda *_args: (_ for _ in ()).throw(
            MercadoLivreError("Mercado Livre respondeu 503: indisponível", status_code=503)
        ),
    )
    monkeypatch.setattr(MercadoLivreClient, "post", lambda *args: posts.append(args))

    sync_module.issue_and_sync_invoice(db, order, account, force_issue=True)

    assert posts == []
    assert order.fiscal_status == "error"
    assert "503" in order.fiscal_error


def test_empty_follow_up_lookup_does_not_revert_authorized_invoice(db, monkeypatch):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-TEST-AUTH", marketplace_order_id="126")
    order = MarketplaceOrder(
        external_order_id="126",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
        external_invoice_id="nf-already-authorized",
        fiscal_status="authorized",
    )
    db.add(order)
    db.commit()
    monkeypatch.setattr(
        sync_module,
        "_automation_config",
        lambda _db: SimpleNamespace(auto_issue_invoice=False),
    )
    monkeypatch.setattr(MercadoLivreClient, "get", lambda *_args: [])
    monkeypatch.setattr(
        MercadoLivreClient,
        "post",
        lambda *_args: (_ for _ in ()).throw(AssertionError("não deve solicitar novamente")),
    )

    sync_module.issue_and_sync_invoice(db, order, account)

    assert order.fiscal_status == "authorized"
    assert order.external_invoice_id == "nf-already-authorized"


def test_label_waits_until_mercado_livre_releases_printing_substatus(db, monkeypatch, tmp_path):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-LABEL-001", marketplace_order_id="456")
    order = MarketplaceOrder(
        external_order_id="456",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        shipment_id="789",
        invoice=invoice,
    )
    db.add(order)
    db.commit()
    shipment = {
        "status": "ready_to_ship",
        "substatus": "invoice_pending",
        "mode": "me2",
        "logistic_type": "drop_off",
    }
    downloads = []
    monkeypatch.setattr(MercadoLivreClient, "get", lambda self, path, **kwargs: shipment)
    monkeypatch.setattr(sync_module, "sync_shipping_history", lambda *args: None)
    monkeypatch.setattr(
        MercadoLivreClient,
        "download",
        lambda self, path: downloads.append(path) or b"label-pdf",
    )
    monkeypatch.setattr(
        sync_module,
        "get_settings",
        lambda: SimpleNamespace(documents_dir=str(tmp_path), mercadolivre_label_format="pdf"),
    )

    sync_module.sync_shipping_label(db, order, account)
    assert order.shipping_substatus == "invoice_pending"
    assert order.label_status == "waiting"
    assert downloads == []
    label_doc = db.scalar(
        select(InvoiceDocument).where(InvoiceDocument.document_type == "label_pdf")
    )
    assert label_doc is None

    shipment["substatus"] = "ready_to_print"
    sync_module.sync_shipping_label(db, order, account)
    assert order.shipping_substatus == "ready_to_print"
    assert order.label_status == "downloaded"
    assert downloads == ["/shipment_labels?shipment_ids=789&response_type=pdf"]
    label_doc = db.scalar(
        select(InvoiceDocument).where(InvoiceDocument.document_type == "label_pdf")
    )
    assert label_doc is not None


def test_manual_invoice_request_immediately_refreshes_label(db, monkeypatch):
    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-FISCAL-LABEL-001", marketplace_order_id="457")
    order = MarketplaceOrder(
        external_order_id="457",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        shipment_id="790",
        invoice=invoice,
    )
    db.add(order)
    db.commit()
    calls = []
    monkeypatch.setattr(
        sync_module,
        "issue_and_sync_invoice",
        lambda _db, _order, _account, **kwargs: calls.append(("invoice", kwargs)),
    )
    monkeypatch.setattr(
        sync_module,
        "sync_shipping_label",
        lambda _db, _order, _account: calls.append(("label", {})),
    )

    updated = request_order_fiscal_document(order.id, db, None)

    assert updated.id == order.id
    assert calls == [("invoice", {"force_issue": True}), ("label", {})]


def test_pending_document_automation_is_retryable_by_background_worker(db, monkeypatch):
    from datetime import UTC, datetime, timedelta

    account = marketplace_account(db)
    invoice = SalesInvoice(number="VEN-AUTO-001", marketplace_order_id="458")
    order = MarketplaceOrder(
        external_order_id="458",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
        fiscal_status="authorized",
        label_status="waiting",
        automation_updated_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    db.add(order)
    db.commit()
    calls = []

    def fake_automate(_db, candidate, connected_account=None):
        calls.append((candidate.id, connected_account))
        candidate.label_status = "downloaded"

    monkeypatch.setattr(sync_module, "automate_order_documents", fake_automate)

    retried = sync_module.retry_pending_automations(db)

    assert retried == 1
    assert calls == [(order.id, None)]


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
        if path.startswith("/visits/items?"):
            return {}
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


def test_marketplace_cancellation_keeps_invoice_and_restores_stock_once(db, monkeypatch):
    marketplace_account(db)
    product = Product(
        sku="CANCEL-001",
        name="Peça cancelada",
        sale_price=Decimal("80"),
        current_stock=Decimal("3"),
    )
    db.add(product)
    db.commit()
    order = {
        "id": 321,
        "seller": {"id": 77},
        "status": "paid",
        "date_created": "2026-08-15T12:30:00.000-04:00",
        "buyer": {"id": 19, "first_name": "João", "last_name": "Cliente"},
        "order_items": [{"item": {"seller_sku": "CANCEL-001"}, "quantity": 1, "unit_price": 80}],
    }
    monkeypatch.setattr(MercadoLivreClient, "get", lambda self, path: order)
    monkeypatch.setattr(
        sync_module,
        "_automation_config",
        lambda db: SimpleNamespace(
            import_orders=True,
            automatic_stock=True,
            sync_documents=False,
            auto_issue_invoice=False,
            auto_download_label=False,
        ),
    )

    record = sync_module.sync_order(db, "77", "/orders/321")
    invoice = db.get(sync_module.SalesInvoice, record.invoice_id)
    assert invoice is not None
    assert invoice.status.value == "confirmed"
    assert product.current_stock == Decimal("2")
    assert invoice.issued_at.isoformat().startswith("2026-08-15T16:30:00")

    order["status"] = "cancelled"
    order["cancel_detail"] = {"description": "Devolução solicitada pelo comprador"}
    record = sync_module.sync_order(db, "77", "/orders/321")
    assert record.invoice_id == invoice.id
    assert invoice.status.value == "cancelled"
    assert product.current_stock == Decimal("3")
    history = list(
        db.scalars(
            select(sync_module.MarketplaceOrderEvent).where(
                sync_module.MarketplaceOrderEvent.order_id == record.id,
                sync_module.MarketplaceOrderEvent.event_type == "after_sale",
            )
        )
    )
    assert len(history) == 1
    assert history[0].detail == "Devolução solicitada pelo comprador"

    sync_module.sync_order(db, "77", "/orders/321")
    assert product.current_stock == Decimal("3")
    assert invoice.status.value == "cancelled"
