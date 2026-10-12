from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AfterSaleCase,
    InvoiceItem,
    MarketplaceOrder,
    SalesInvoice,
)
from app.schemas.common import (
    AfterSaleCaseOut,
    InvoiceAfterSaleOut,
    InvoiceTrackingEventOut,
)


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
    cases = db.scalars(
        select(AfterSaleCase)
        .options(selectinload(AfterSaleCase.items), selectinload(AfterSaleCase.events))
        .where(AfterSaleCase.invoice_id.in_([invoice.id for invoice in invoices]))
    )
    case_by_invoice: dict[str, list[AfterSaleCaseOut]] = {}
    for case in cases:
        if case.invoice_id:
            case_by_invoice.setdefault(case.invoice_id, []).append(
                AfterSaleCaseOut.model_validate(case)
            )
    result: dict[str, InvoiceAfterSaleOut] = {}
    for invoice in invoices:
        order = by_external_id.get(invoice.marketplace_order_id or "")
        if order:
            after_sale = invoice_after_sale(order, invoice.total)
            if after_sale:
                case = case_by_invoice.get(invoice.id)
                if case:
                    after_sale.cases = case
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


def _case_requested_quantity(
    case_data: dict[str, Any], order_payload: dict[str, Any], invoice_item: InvoiceItem
) -> Decimal:
    raw_items = case_data.get("return_items") or case_data.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("items", [])
    order_items = order_payload.get("order_items", [])
    if not isinstance(raw_items, list) or not isinstance(order_items, list):
        return Decimal(invoice_item.quantity)
    invoice_lines = order_payload.get("order_items", [])
    can_match_unidentified_line = len(invoice_lines) <= 1
    for returned in raw_items:
        if not isinstance(returned, dict):
            continue
        returned_item = returned.get("item") if isinstance(returned.get("item"), dict) else returned
        sku = _first_text(
            returned.get("seller_sku"),
            returned.get("seller_custom_field"),
            returned_item.get("seller_sku"),
            returned_item.get("seller_custom_field"),
        )
        external_item_id = _first_text(returned_item.get("id"), returned.get("item_id"))
        if not sku and external_item_id:
            for order_line in order_items:
                if not isinstance(order_line, dict):
                    continue
                order_item = (
                    order_line.get("item") if isinstance(order_line.get("item"), dict) else {}
                )
                if str(order_item.get("id") or "") == external_item_id:
                    sku = _first_text(
                        order_line.get("seller_sku"), order_line.get("seller_custom_field")
                    )
                    break
        if not sku and not can_match_unidentified_line:
            continue
        if sku and sku != invoice_item.sku:
            continue
        quantity = (
            returned.get("quantity")
            or returned.get("return_quantity")
            or returned.get("requested_quantity")
        )
        if quantity is not None:
            try:
                parsed = Decimal(str(quantity))
                if parsed > 0:
                    return min(parsed, Decimal(invoice_item.quantity))
            except InvalidOperation:
                pass
    # Some ML return notifications omit per-line quantities. Keep the sold quantity
    # as the ceiling; staff records the physical quantity actually received.
    return Decimal(invoice_item.quantity)


def after_sale_case_output(case: AfterSaleCase) -> AfterSaleCaseOut:
    return AfterSaleCaseOut.model_validate(case)
