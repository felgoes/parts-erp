from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AfterSaleCase,
    AfterSaleCaseEvent,
    AfterSaleCaseItem,
    InvoiceItem,
    InvoiceStatus,
    MarketplaceOrder,
    MovementType,
    SalesInvoice,
    StockMovement,
    User,
)
from app.schemas.common import (
    AfterSaleInspectIn,
    AfterSaleReceiveIn,
    AfterSaleCaseOut,
    InvoiceAfterSaleOut,
    InvoiceTrackingEventOut,
)
from app.services.stock import move_stock


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
            case_by_invoice.setdefault(case.invoice_id, []).append(AfterSaleCaseOut.model_validate(case))
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
                order_item = order_line.get("item") if isinstance(order_line.get("item"), dict) else {}
                if str(order_item.get("id") or "") == external_item_id:
                    sku = _first_text(
                        order_line.get("seller_sku"), order_line.get("seller_custom_field")
                    )
                    break
        if not sku and not can_match_unidentified_line:
            continue
        if sku and sku != invoice_item.sku:
            continue
        quantity = returned.get("quantity") or returned.get("return_quantity") or returned.get("requested_quantity")
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


def upsert_after_sale_case(
    db: Session,
    order: MarketplaceOrder,
    event_data: dict[str, Any],
    case_data: dict[str, Any],
    external_case_id: str,
) -> AfterSaleCase:
    invoice = db.get(SalesInvoice, order.invoice_id) if order.invoice_id else None
    order_payload = order.payload if isinstance(order.payload, dict) else {}
    payments = order_payload.get("payments") if isinstance(order_payload.get("payments"), list) else []
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
            payload={"notification": {key: event_data.get(key) for key in ("kind", "status", "id")}},
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
        case.payload = {"notification": {key: event_data.get(key) for key in ("kind", "status", "id")}}

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


def receive_after_sale_items(
    db: Session, case: AfterSaleCase, payload: AfterSaleReceiveIn, actor: User
) -> AfterSaleCase:
    if case.workflow_status in {"resolved", "cancelled"}:
        raise ValueError("Este pós-venda já foi encerrado")
    requested = {row.item_id: row.received_quantity for row in payload.items}
    if len(requested) != len(payload.items):
        raise ValueError("Não repita o mesmo item na lista")
    for item_id, quantity in requested.items():
        item = next((row for row in case.items if row.id == item_id), None)
        if not item:
            raise ValueError("Peça não pertence a este pós-venda")
        current = Decimal(item.received_quantity)
        target = Decimal(quantity)
        if target < current or target > Decimal(item.requested_quantity):
            raise ValueError(
                f"Quantidade recebida deve ficar entre {current} e {item.requested_quantity} para {item.sku}"
            )
        if target == current:
            continue
        item.received_quantity = target
        detail = f"Recebidas {target} de {item.requested_quantity} un. · {item.sku} · {actor.full_name}"
        _record_case_event(
            db,
            case,
            event_type="receipt",
            status="received",
            detail=detail,
            fingerprint=f"receipt:{item.id}:{format(target.normalize(), 'f')}",
            actor=actor,
        )
        if payload.notes:
            item.notes = payload.notes
    received_any = any(Decimal(item.received_quantity) > 0 for item in case.items)
    all_received = bool(case.items) and all(
        Decimal(item.received_quantity) >= Decimal(item.requested_quantity) for item in case.items
    )
    case.workflow_status = "inspection_pending" if all_received else "partially_received" if received_any else "requested"
    db.flush()
    return case


def inspect_after_sale_items(
    db: Session, case: AfterSaleCase, payload: AfterSaleInspectIn, actor: User
) -> AfterSaleCase:
    if case.workflow_status in {"resolved", "cancelled"}:
        raise ValueError("Este pós-venda já foi encerrado")
    requested = {row.item_id: row for row in payload.items}
    if len(requested) != len(payload.items):
        raise ValueError("Não repita o mesmo item na lista")
    invoice = db.get(SalesInvoice, case.invoice_id) if case.invoice_id else None
    if not invoice:
        raise ValueError("O pós-venda ainda não está vinculado a uma fatura")
    if invoice.status == InvoiceStatus.cancelled:
        raise ValueError("A venda cancelada já teve o estoque estornado; confira o saldo antes de lançar outra entrada")

    for item_id, decision in requested.items():
        item = next((row for row in case.items if row.id == item_id), None)
        if not item:
            raise ValueError("Peça não pertence a este pós-venda")
        received = Decimal(item.received_quantity)
        target = Decimal(decision.restock_quantity)
        current_restocked = Decimal(item.restocked_quantity)
        if received <= 0:
            raise ValueError(f"Registre primeiro o recebimento físico de {item.sku}")
        if target < current_restocked or target > received:
            raise ValueError(
                f"Quantidade de retorno ao estoque deve ficar entre {current_restocked} e {received} para {item.sku}"
            )
        if decision.disposition == "restock" and target != received:
            raise ValueError("Para aprovar todas as unidades, a quantidade de retorno ao estoque deve igualar a recebida")
        if decision.disposition in {"damaged", "discarded"} and target != 0:
            raise ValueError("Peça danificada ou descartada não pode gerar entrada no estoque")
        if decision.disposition == "mixed" and not (Decimal("0") < target < received):
            raise ValueError("Informe uma quantidade parcial para o destino misto")

        delta = target - current_restocked
        if delta > 0:
            original_sale = db.scalar(
                select(StockMovement).where(
                    StockMovement.idempotency_key
                    == f"invoice:{invoice.id}:item:{item.invoice_item_id}:confirm"
                )
            )
            move_stock(
                db,
                product_id=item.product_id,
                quantity=delta,
                movement_type=MovementType.customer_return,
                reason=f"Devolução ML #{case.marketplace_order_id} · caso {case.external_case_id}",
                reference=invoice.id,
                idempotency_key=(
                    f"return:{case.id}:{item.id}:restock:{format(target.normalize(), 'f')}"
                ),
                unit_cost=original_sale.unit_cost if original_sale else None,
            )
        item.inspected_quantity = received
        item.restocked_quantity = target
        item.disposition = "mixed" if 0 < target < received else decision.disposition
        item.notes = decision.notes or item.notes
        detail = (
            f"Inspecionadas {received} un. de {item.sku}; {target} un. voltaram ao estoque; "
            f"destino: {item.disposition} · {actor.full_name}"
        )
        _record_case_event(
            db,
            case,
            event_type="inspection",
            status=item.disposition,
            detail=detail,
            fingerprint=(
                f"inspection:{item.id}:{format(received.normalize(), 'f')}:"
                f"{format(target.normalize(), 'f')}:{item.disposition}"
            ),
            actor=actor,
        )

    all_received = bool(case.items) and all(
        Decimal(item.received_quantity) >= Decimal(item.requested_quantity) for item in case.items
    )
    all_inspected = bool(case.items) and all(
        Decimal(item.inspected_quantity) >= Decimal(item.received_quantity) for item in case.items
    )
    if all_received and all_inspected:
        case.workflow_status = "resolved"
        case.completed_at = datetime.now(UTC)
    else:
        case.workflow_status = "inspection_pending" if any(
            Decimal(item.received_quantity) > Decimal(item.inspected_quantity) for item in case.items
        ) else "partially_received"
    db.flush()
    return case


def close_after_sale_without_stock(
    db: Session, case: AfterSaleCase, note: str, actor: User
) -> AfterSaleCase:
    if any(Decimal(item.received_quantity) > Decimal(item.inspected_quantity) for item in case.items):
        raise ValueError("Há peças recebidas que ainda precisam de inspeção")
    if any(Decimal(item.received_quantity) > 0 for item in case.items) and not all(
        Decimal(item.inspected_quantity) >= Decimal(item.received_quantity) for item in case.items
    ):
        raise ValueError("Inspecione as peças recebidas antes de encerrar o caso")
    case.workflow_status = "resolved"
    case.completed_at = datetime.now(UTC)
    case.notes = note
    _record_case_event(
        db,
        case,
        event_type="resolution",
        status="resolved_without_stock",
        detail=f"Encerrado sem nova entrada de estoque: {note} · {actor.full_name}",
        fingerprint=f"close-without-stock:{case.id}:{note.strip()[:100]}",
        actor=actor,
    )
    db.flush()
    return case


def after_sale_case_output(case: AfterSaleCase) -> AfterSaleCaseOut:
    return AfterSaleCaseOut.model_validate(case)
