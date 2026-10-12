from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AfterSaleCase,
    AfterSaleCaseEvent,
    AfterSaleCaseItem,
    MarketplaceOrder,
    SalesInvoice,
    User,
)
from app.services.after_sale_reading import (
    _case_requested_quantity,
    _date,
    _first_text,
    _refund_amount,
)


def upsert_after_sale_case(
    db: Session,
    order: MarketplaceOrder,
    event_data: dict[str, Any],
    case_data: dict[str, Any],
    external_case_id: str,
) -> AfterSaleCase:
    invoice = db.get(SalesInvoice, order.invoice_id) if order.invoice_id else None
    order_payload = order.payload if isinstance(order.payload, dict) else {}
    payments = (
        order_payload.get("payments") if isinstance(order_payload.get("payments"), list) else []
    )
    refunded_payment = next(
        (
            payment
            for payment in payments
            if isinstance(payment, dict)
            and str(payment.get("status", "")).lower() in {"refunded", "partially_refunded"}
        ),
        {},
    )
    refund_amount = _refund_amount(payments, Decimal(invoice.total)) if invoice else None
    payment_status = _first_text(refunded_payment.get("status"))
    provider = order.provider or "mercadolivre"
    case = db.scalar(
        select(AfterSaleCase).where(
            AfterSaleCase.provider == provider,
            AfterSaleCase.external_case_id == external_case_id,
        )
    )
    if not case:
        case = AfterSaleCase(
            provider=provider,
            external_case_id=external_case_id,
            marketplace_order_id=order.id,
            invoice_id=invoice.id if invoice else None,
            kind=str(event_data.get("kind") or "return"),
            workflow_status="requested",
            marketplace_status=str(event_data.get("status") or "unknown"),
            reason=event_data.get("reason"),
            requested_by=event_data.get("requested_by"),
            payment_status=payment_status,
            refund_amount=refund_amount,
            requested_at=_date(event_data.get("created_at")),
            payload={
                "notification": {key: event_data.get(key) for key in ("kind", "status", "id")}
            },
        )
        db.add(case)
        db.flush()
    else:
        case.marketplace_order_id = order.id
        case.invoice_id = invoice.id if invoice else case.invoice_id
        case.marketplace_status = str(event_data.get("status") or case.marketplace_status)
        case.reason = event_data.get("reason") or case.reason
        case.requested_by = event_data.get("requested_by") or case.requested_by
        case.payment_status = payment_status or case.payment_status
        case.refund_amount = refund_amount if refund_amount is not None else case.refund_amount
        case.requested_at = case.requested_at or _date(event_data.get("created_at"))
        case.payload = {
            "notification": {key: event_data.get(key) for key in ("kind", "status", "id")}
        }

    if invoice and not case.items:
        for invoice_item in invoice.items:
            case.items.append(
                AfterSaleCaseItem(
                    invoice_item_id=invoice_item.id,
                    product_id=invoice_item.product_id,
                    sku=invoice_item.sku,
                    description=invoice_item.description,
                    requested_quantity=_case_requested_quantity(
                        case_data, order_payload, invoice_item
                    ),
                )
            )

    status = str(event_data.get("status") or "unknown")[:60]
    fingerprint = f"marketplace:{event_data.get('kind')}:{external_case_id}:{status}"[:180]
    if not db.scalar(
        select(AfterSaleCaseEvent.id).where(
            AfterSaleCaseEvent.case_id == case.id,
            AfterSaleCaseEvent.fingerprint == fingerprint,
        )
    ):
        db.add(
            AfterSaleCaseEvent(
                case_id=case.id,
                event_type="marketplace_update",
                status=status,
                detail=event_data.get("reason"),
                fingerprint=fingerprint,
                payload={key: value for key, value in event_data.items() if value is not None},
                created_at=_date(event_data.get("created_at")) or datetime.now(UTC),
            )
        )
    db.flush()
    return case


def link_pending_after_sale_cases(
    db: Session, order: MarketplaceOrder, invoice: SalesInvoice
) -> None:
    cases = list(
        db.scalars(
            select(AfterSaleCase).where(
                AfterSaleCase.marketplace_order_id == order.id,
                AfterSaleCase.invoice_id.is_(None),
            )
        )
    )
    for case in cases:
        case.invoice_id = invoice.id
        if not case.items:
            for invoice_item in invoice.items:
                case.items.append(
                    AfterSaleCaseItem(
                        invoice_item_id=invoice_item.id,
                        product_id=invoice_item.product_id,
                        sku=invoice_item.sku,
                        description=invoice_item.description,
                        requested_quantity=Decimal(invoice_item.quantity),
                    )
                )
    if cases:
        db.flush()


def _record_case_event(
    db: Session,
    case: AfterSaleCase,
    *,
    event_type: str,
    status: str,
    detail: str,
    fingerprint: str,
    actor: User,
) -> None:
    if db.scalar(
        select(AfterSaleCaseEvent.id).where(
            AfterSaleCaseEvent.case_id == case.id,
            AfterSaleCaseEvent.fingerprint == fingerprint,
        )
    ):
        return
    db.add(
        AfterSaleCaseEvent(
            case_id=case.id,
            event_type=event_type,
            status=status,
            detail=detail[:500],
            fingerprint=fingerprint[:180],
            payload={"actor": actor.full_name},
            created_at=datetime.now(UTC),
        )
    )
