from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre import ml_support
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.ml_support import (
    PRINTABLE_LOGISTICS,
    TERMINAL_SHIPPING_STATUSES,
    _parse_event_datetime,
    _store_document,
)
from app.models import (
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceOrder,
    MarketplaceOrderEvent,
)
from app.services.tracking_destination import persist_tracking_destination


def _shipping_cost_metadata(record: MarketplaceOrder, **values: Any) -> None:
    record.payload = {**(record.payload or {}), **values}


def sync_shipping_status(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount
) -> dict[str, Any] | None:
    """Refresh shipment state and its Mercado Envios timeline, independent of label state."""
    if not record.shipment_id:
        return None
    client = MercadoLivreClient(db, account)
    shipment = client.get(
        f"/shipments/{record.shipment_id}", extra_headers={"x-format-new": "true"}
    )
    if not isinstance(shipment, dict):
        raise MercadoLivreError("Resposta de envio inválida")
    record.shipping_status = str(shipment.get("status") or record.shipping_status or "unknown")
    record.shipping_substatus = str(shipment.get("substatus") or "") or None
    persist_tracking_destination(record, shipment)
    sync_shipping_history(db, record, account)
    return shipment


def sync_seller_shipping_cost(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount
) -> Decimal | None:
    """Persist the final shipping amount charged to this seller.

    O Mercado Livre diferencia o custo do comprador (`receiver.cost`) do que
    efetivamente fica com o vendedor (`senders[].cost`). O pedido, sozinho, não
    serve para conciliação quando há frete grátis, subsídio ou reputação.
    """
    synced_at = datetime.now(UTC).isoformat()
    if not record.shipment_id:
        _shipping_cost_metadata(
            record,
            _erp_seller_shipping_cost="0",
            _erp_shipping_cost_synced_at=synced_at,
            _erp_shipping_cost_error=None,
        )
        return Decimal("0")

    try:
        result = MercadoLivreClient(db, account).get(
            f"/shipments/{record.shipment_id}/costs",
            extra_headers={"x-format-new": "true"},
        )
        senders = result.get("senders") if isinstance(result, dict) else None
        candidates = [item for item in senders or [] if isinstance(item, dict)]
        matching = [
            item
            for item in candidates
            if str(
                item.get("sender_id") or item.get("user_id") or item.get("id") or ""
            )
            == str(record.seller_id)
        ]
        if not matching and len(candidates) == 1:
            matching = candidates
        if not matching:
            raise MercadoLivreError("O custo do vendedor não foi informado no envio")
        values = [
            Decimal(str(item.get("cost")))
            for item in matching
            if item.get("cost") is not None
        ]
        if len(values) != len(matching):
            raise MercadoLivreError("O envio veio sem o valor final do vendedor")
        cost = sum(values, Decimal("0"))
    except (MercadoLivreError, InvalidOperation, ValueError) as exc:
        _shipping_cost_metadata(record, _erp_shipping_cost_error=str(exc)[:500])
        return None

    _shipping_cost_metadata(
        record,
        _erp_seller_shipping_cost=str(cost),
        _erp_shipping_cost_synced_at=synced_at,
        _erp_shipping_cost_error=None,
    )
    return cost


def sync_shipping_label(db: Session, record: MarketplaceOrder, account: MarketplaceAccount) -> None:
    if not record.invoice_id:
        return
    if not record.shipment_id:
        record.label_status = "waiting_shipment"
        record.label_error = None
        return
    if record.label_status == "downloaded" and db.scalar(
        select(InvoiceDocument.id).where(
            InvoiceDocument.invoice_id == record.invoice_id,
            InvoiceDocument.document_type == "label_pdf",
        )
    ):
        return
    client = MercadoLivreClient(db, account)
    try:
        shipment = sync_shipping_status(db, record, account)
        if shipment is None:
            raise MercadoLivreError("Resposta de envio inválida")

        # Depois que o pedido já foi entregue/devolvido, a janela operacional
        # da etiqueta foi encerrada. Não devemos mostrar "Aguardando envio"
        # indefinidamente só porque a etiqueta não foi arquivada pelo ERP.
        # Se ela já estiver anexada, preservamos o status "Baixada".
        if record.shipping_status.lower() in TERMINAL_SHIPPING_STATUSES:
            has_label = db.scalar(
                select(InvoiceDocument.id).where(
                    InvoiceDocument.invoice_id == record.invoice_id,
                    InvoiceDocument.document_type == "label_pdf",
                )
            )
            if not has_label:
                record.label_status = "completed"
                record.label_error = None
            return

        logistic_value = shipment.get("logistic")
        logistic: dict[str, Any] = logistic_value if isinstance(logistic_value, dict) else {}
        logistic_type = str(shipment.get("logistic_type") or logistic.get("type") or "")
        mode = str(shipment.get("mode") or logistic.get("mode") or "")
        if mode != "me2" or logistic_type not in PRINTABLE_LOGISTICS:
            record.label_status = "not_applicable"
            record.label_error = None
            return
        if record.shipping_status != "ready_to_ship" or record.shipping_substatus not in {
            "ready_to_print",
            "printed",
        }:
            record.label_status = "waiting"
            record.label_error = None
            return
        if ml_support.get_settings().mercadolivre_label_format.lower() != "pdf":
            raise MercadoLivreError("Apenas etiquetas PDF são suportadas nesta versão")
        _store_document(
            db,
            str(record.invoice_id),
            f"shipment:{record.shipment_id}:label_pdf",
            "label_pdf",
            f"etiqueta-{record.shipment_id}.pdf",
            client.download(
                f"/shipment_labels?shipment_ids={record.shipment_id}&response_type=pdf"
            ),
        )
        record.label_status = "downloaded"
        record.label_error = None
    except MercadoLivreError as exc:
        record.label_status = "error"
        record.label_error = str(exc)[:1000]


def sync_shipping_history(
    db: Session, record: MarketplaceOrder, account: MarketplaceAccount
) -> None:
    """Import the shipment timeline exposed by Mercado Livre's history endpoint."""
    if not record.shipment_id:
        return
    client = MercadoLivreClient(db, account)
    try:
        result = client.get(
            f"/shipments/{record.shipment_id}/history",
            extra_headers={"x-format-new": "true"},
        )
    except MercadoLivreError:
        return
    entries: Any
    if isinstance(result, list):
        entries = result
    elif isinstance(result, dict):
        entries = result.get("history") or result.get("events") or result.get("results") or []
    else:
        entries = []
    if not isinstance(entries, list):
        return
    existing = list(
        db.scalars(
            select(MarketplaceOrderEvent).where(
                MarketplaceOrderEvent.order_id == record.id,
                MarketplaceOrderEvent.event_type == "shipment_status",
            )
        )
    )
    known = {
        (
            event.status,
            event.detail,
            str((event.payload or {}).get("source_date") or ""),
        )
        for event in existing
    }
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("shipment_status") or "").strip()
        if not status:
            continue
        substatus = item.get("substatus") or item.get("sub_status")
        detail = (
            str(substatus or item.get("detail") or item.get("description") or "").strip() or None
        )
        source_date = str(
            item.get("date") or item.get("created_at") or item.get("updated_at") or ""
        ).strip()
        key = (status, detail, source_date)
        if key in known:
            continue
        payload = dict(item)
        payload["source_date"] = source_date
        db.add(
            MarketplaceOrderEvent(
                order_id=record.id,
                event_type="shipment_status",
                status=status,
                detail=detail,
                payload=payload,
                created_at=_parse_event_datetime(source_date) or datetime.now(UTC),
            )
        )
        known.add(key)
    db.commit()
