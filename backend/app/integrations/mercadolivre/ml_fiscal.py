from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre import ml_support
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.ml_shipping import (
    sync_shipping_label,
    sync_shipping_status,
)
from app.integrations.mercadolivre.ml_support import (
    FINISHED_FISCAL_STATUSES,
    FINISHED_LABEL_STATUSES,
    _account,
    _fiscal_entries,
    _store_document,
)
from app.models import (
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceOrder,
)


def sync_invoice_documents(
    db: Session,
    account: MarketplaceAccount,
    order_id: str,
    invoice_id: str,
    order: dict[str, Any] | None = None,
) -> int:
    del order  # Mantido para compatibilidade com chamadas antigas.
    client = MercadoLivreClient(db, account)
    result = client.get(f"/users/{account.seller_id}/invoices/orders/{order_id}")
    saved = 0
    for fiscal in _fiscal_entries(result):
        if str(fiscal.get("status", "")).lower() != "authorized":
            continue
        external_id = str(fiscal.get("id", order_id))
        attributes = fiscal.get("attributes") if isinstance(fiscal.get("attributes"), dict) else {}
        locations = {
            "xml": fiscal.get("xml_location") or attributes.get("xml_location"),
            "pdf": fiscal.get("danfe_location") or attributes.get("danfe_location"),
        }
        for document_type, location in locations.items():
            document_external_id = f"{external_id}:{document_type}"
            existing = db.scalar(
                select(InvoiceDocument).where(
                    InvoiceDocument.invoice_id == invoice_id,
                    InvoiceDocument.external_id == document_external_id,
                )
            )
            if existing or not location:
                continue
            saved += int(
                _store_document(
                    db,
                    invoice_id,
                    document_external_id,
                    document_type,
                    f"nfe-{external_id}.{document_type}",
                    client.download(str(location)),
                )
            )
    db.commit()
    return saved


def issue_and_sync_invoice(
    db: Session,
    record: MarketplaceOrder,
    account: MarketplaceAccount,
    *,
    force_issue: bool = False,
) -> None:
    if not record.invoice_id:
        return
    client = MercadoLivreClient(db, account)
    fiscal_entries: list[dict[str, Any]] = []
    config = ml_support._automation_config(db)
    auto_issue = record.status.lower() not in {"cancelled", "canceled"} and (
        force_issue
        or (
            config.auto_issue_invoice
            if config
            else ml_support.get_settings().mercadolivre_auto_issue_invoice
        )
    )
    try:
        try:
            result = client.get(
                f"/users/{account.seller_id}/invoices/orders/{record.external_order_id}"
            )
            fiscal_entries = _fiscal_entries(result)
        except MercadoLivreError as exc:
            if exc.status_code != 404:
                raise

        if not fiscal_entries and auto_issue and not record.external_invoice_id:
            if record.shipment_id:
                sync_shipping_status(db, record, account)
                if record.shipping_status not in {"ready_to_ship", "shipped", "delivered"}:
                    record.fiscal_status = "waiting_release"
                    record.fiscal_error = None
                    return
            record.fiscal_status = "requesting"
            db.commit()
            result = client.post(
                f"/users/{account.seller_id}/invoices/orders",
                {"orders": [int(record.external_order_id)]},
            )
            fiscal_entries = _fiscal_entries(result)

        statuses = {str(item.get("status", "pending")).lower() for item in fiscal_entries}
        first_id = next((item.get("id") for item in fiscal_entries if item.get("id")), None)
        if first_id:
            record.external_invoice_id = str(first_id)
        if "authorized" in statuses:
            sync_invoice_documents(db, account, record.external_order_id, str(record.invoice_id))
            record.fiscal_status = "authorized"
        elif statuses:
            record.fiscal_status = sorted(statuses)[0]
        elif record.external_invoice_id and record.fiscal_status == "authorized":
            # Uma consulta temporariamente vazia não deve desfazer uma NF-e
            # que já foi confirmada anteriormente pelo Mercado Livre.
            record.fiscal_status = "authorized"
        else:
            record.fiscal_status = "pending"
        record.fiscal_error = None
    except MercadoLivreError as exc:
        # The shipment can change between GET and issuance; this specific
        # rejection is an expected wait, unlike other fiscal validation errors.
        if exc.status_code == 400 and "shipment status is not ready_to_ship" in str(exc).lower():
            record.fiscal_status = "waiting_release"
            record.fiscal_error = None
        else:
            record.fiscal_status = "error"
            record.fiscal_error = str(exc)[:1000]


def automate_order_documents(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount | None = None
) -> MarketplaceOrder:
    if not record.invoice_id:
        return record
    connected_account = account or _account(db, record.seller_id)
    issue_and_sync_invoice(db, record, connected_account)
    config = ml_support._automation_config(db)
    download_label = (
        config.auto_download_label
        if config
        else getattr(ml_support.get_settings(), "mercadolivre_auto_download_label", True)
    )
    if download_label:
        sync_shipping_label(db, record, connected_account)
    record.automation_updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    return record


def retry_pending_automations(db: Session) -> int:
    now = datetime.now(UTC)
    recent_order = now - timedelta(minutes=10)
    fast_cutoff = now - timedelta(minutes=2)
    slow_cutoff = now - timedelta(minutes=5)
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.invoice_id.is_not(None),
                or_(
                    MarketplaceOrder.automation_updated_at.is_(None),
                    (MarketplaceOrder.created_at >= recent_order)
                    & (MarketplaceOrder.automation_updated_at <= fast_cutoff),
                    MarketplaceOrder.automation_updated_at <= slow_cutoff,
                ),
                MarketplaceOrder.status.not_in({"cancelled", "canceled"}),
                (
                    MarketplaceOrder.fiscal_status.not_in(FINISHED_FISCAL_STATUSES)
                    | MarketplaceOrder.label_status.not_in(FINISHED_LABEL_STATUSES)
                ),
            )
            .order_by(MarketplaceOrder.automation_updated_at.asc(), MarketplaceOrder.id)
            .limit(20)
        )
    )
    for order in orders:
        automate_order_documents(db, order)
    return len(orders)
