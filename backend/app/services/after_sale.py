from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceOrder, SalesInvoice
from app.schemas.common import InvoiceAfterSaleOut, InvoiceTrackingEventOut


def _first_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    return {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _refund_amount(payments: list[Any], total: Decimal) -> Decimal | None:
    refund_statuses = {"refunded", "partially_refunded"}
    refunded = [
        item
        for item in payments
        if isinstance(item, dict) and str(item.get("status", "")).lower() in refund_statuses
    ]
    if not refunded:
        return None
    amounts: list[Decimal] = []
    for payment in refunded:
        for key in ("refunded_amount", "refund_amount"):
            raw = payment.get(key)
            if raw is not None:
                try:
                    amounts.append(Decimal(str(raw)))
                except InvalidOperation:
                    pass
                break
    if amounts:
        return sum(amounts, Decimal("0"))
    if all(str(item.get("status", "")).lower() == "refunded" for item in refunded):
        return total
    return None


def invoice_after_sale(
    order: MarketplaceOrder, invoice_total: Decimal
) -> InvoiceAfterSaleOut | None:
    payload = order.payload if isinstance(order.payload, dict) else {}
    saved_events = payload.get("_erp_after_sale_events")
    saved_events = saved_events if isinstance(saved_events, list) else []
    latest_event = _first_record(saved_events[-1:] if saved_events else [])
    returns = (
        payload.get("returns")
        or payload.get("claims")
        or (latest_event if latest_event.get("kind") in {"return", "claim"} else None)
    )
    return_record = _first_record(returns)
    cancel = payload.get("cancel_detail")
    cancel_record = cancel if isinstance(cancel, dict) else {}
    payments = payload.get("payments")
    payments = payments if isinstance(payments, list) else []
    payment = next(
        (
            item
            for item in payments
            if isinstance(item, dict)
            and str(item.get("status", "")).lower() in {"refunded", "partially_refunded"}
        ),
        {},
    )
    order_status = str(order.status or "").lower()
    is_cancelled = order_status in {"cancelled", "canceled"}
    if not returns and not cancel_record and not is_cancelled and not payment:
        return None

    has_return = bool(payload.get("returns")) or bool(
        latest_event and latest_event.get("kind") == "return"
    )
    has_claim = bool(payload.get("claims")) or bool(
        latest_event and latest_event.get("kind") == "claim"
    )
    reason = _first_text(
        return_record.get("reason"),
        return_record.get("reason_description"),
        return_record.get("description"),
        return_record.get("substatus"),
        cancel_record.get("description"),
    )
    requested_by = _first_text(return_record.get("requested_by"), cancel_record.get("requested_by"))
    status = (
        _first_text(
            return_record.get("status"),
            return_record.get("substatus"),
            order_status if is_cancelled else None,
            "return_requested" if has_return else "cancellation_requested",
        )
        or "unknown"
    )

    return InvoiceAfterSaleOut(
        kind="return" if has_return else "claim" if has_claim else "cancellation",
        status=status,
        reason=reason,
        requested_by=requested_by,
        return_id=_first_text(return_record.get("id"), return_record.get("claim_id")),
        payment_status=_first_text(payment.get("status")),
        refund_amount=_refund_amount(payments, invoice_total),
        requested_at=_date(
            return_record.get("date_created")
            or return_record.get("created_at")
            or cancel_record.get("date_created")
            or latest_event.get("created_at")
        ),
        history=[
            InvoiceTrackingEventOut(
                status=str(item.get("status") or "unknown"),
                detail=_first_text(item.get("reason"), item.get("detail")),
                created_at=_date(item.get("created_at")) or order.updated_at,
            )
            for item in saved_events
            if isinstance(item, dict)
        ],
    )


def after_sales_for_invoices(
    db: Session, invoices: list[SalesInvoice]
) -> dict[str, InvoiceAfterSaleOut]:
    external_ids = [
        invoice.marketplace_order_id for invoice in invoices if invoice.marketplace_order_id
    ]
    if not external_ids:
        return {}
    orders = db.scalars(
        select(MarketplaceOrder).where(MarketplaceOrder.external_order_id.in_(external_ids))
    )
    by_external_id = {order.external_order_id: order for order in orders}
    result: dict[str, InvoiceAfterSaleOut] = {}
    for invoice in invoices:
        order = by_external_id.get(invoice.marketplace_order_id or "")
        if order:
            after_sale = invoice_after_sale(order, invoice.total)
            if after_sale:
                result[invoice.id] = after_sale
    return result


def after_sale_notification(topic: str, data: dict[str, Any]) -> dict[str, Any]:
    case = data.get("return") if isinstance(data.get("return"), dict) else data
    status = _first_text(case.get("status"), case.get("stage"))
    reason = _first_text(
        case.get("reason"), case.get("reason_description"), case.get("description")
    )
    created_at = _first_text(
        case.get("date_created"), case.get("created_at"), case.get("last_updated")
    )
    kind = "return" if topic == "returns" else "claim"
    if not status:
        status = "return_requested" if kind == "return" else "claim_opened"
    return {
        "kind": kind,
        "status": status,
        "reason": reason,
        "requested_by": _first_text(case.get("requested_by")),
        "id": _first_text(case.get("id"), case.get("claim_id"), case.get("return_id")),
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }
