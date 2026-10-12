from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AfterSaleCase,
    InvoiceStatus,
    MovementType,
    SalesInvoice,
    StockMovement,
    User,
)
from app.schemas.common import (
    AfterSaleInspectIn,
    AfterSaleReceiveIn,
)
from app.services.after_sale_cases import (
    _record_case_event,
)
from app.services.stock import move_stock


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
                f"Quantidade recebida deve ficar entre {current} e {item.requested_quantity} "
                f"para {item.sku}"
            )
        if target == current:
            continue
        item.received_quantity = target
        detail = (
            f"Recebidas {target} de {item.requested_quantity} un. · {item.sku} · {actor.full_name}"
        )
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
    case.workflow_status = (
        "inspection_pending"
        if all_received
        else "partially_received"
        if received_any
        else "requested"
    )
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
        raise ValueError(
            "A venda cancelada já teve o estoque estornado; confira o saldo antes de "
            "lançar outra entrada"
        )

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
                f"Quantidade de retorno ao estoque deve ficar entre {current_restocked} e "
                f"{received} para {item.sku}"
            )
        if decision.disposition == "restock" and target != received:
            raise ValueError(
                "Para aprovar todas as unidades, a quantidade de retorno ao estoque deve "
                "igualar a recebida"
            )
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
        case.workflow_status = (
            "inspection_pending"
            if any(
                Decimal(item.received_quantity) > Decimal(item.inspected_quantity)
                for item in case.items
            )
            else "partially_received"
        )
    db.flush()
    return case


def close_after_sale_without_stock(
    db: Session, case: AfterSaleCase, note: str, actor: User
) -> AfterSaleCase:
    if any(
        Decimal(item.received_quantity) > Decimal(item.inspected_quantity) for item in case.items
    ):
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
