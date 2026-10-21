from sqlalchemy import select

from app.models import (
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceOrder,
    PushNotification,
    SalesInvoice,
)
from app.services.push_notifications import enqueue_ready_to_ship_notification


def test_ready_to_ship_alert_waits_for_both_documents_and_is_idempotent(db):
    account = MarketplaceAccount(
        seller_id="milestone-seller", encrypted_access_token="x", active=True
    )
    invoice = SalesInvoice(number="MILESTONE-1", marketplace_order_id="789")
    order = MarketplaceOrder(
        external_order_id="789",
        seller_id=account.seller_id,
        status="paid",
        payload={},
        invoice=invoice,
    )
    db.add_all([account, order])
    db.flush()
    db.add(
        InvoiceDocument(
            invoice_id=invoice.id,
            external_id="label-789",
            document_type="label_pdf",
            filename="label.pdf",
            storage_path="/qa/label.pdf",
            sha256="a" * 64,
        )
    )
    db.flush()
    assert enqueue_ready_to_ship_notification(db, order) is None
    db.add(
        InvoiceDocument(
            invoice_id=invoice.id,
            external_id="invoice-789",
            document_type="xml",
            filename="invoice.xml",
            storage_path="/qa/invoice.xml",
            sha256="b" * 64,
        )
    )
    db.flush()

    enqueue_ready_to_ship_notification(db, order)
    enqueue_ready_to_ship_notification(db, order)
    alerts = list(db.scalars(select(PushNotification).order_by(PushNotification.created_at)))

    assert [item.title for item in alerts] == ["Venda confirmada", "Pronto para envio"]
    assert [action["label"] for action in alerts[1].data["actions"]] == [
        "Abrir pedido",
        "Etiqueta",
        "NF-e",
    ]
