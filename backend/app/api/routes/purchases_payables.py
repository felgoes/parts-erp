from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_support import (
    PAYABLE_TERM_DAYS,
    _as_utc,
    _event,
    _load,
    _purchase_total,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    PayablePayment,
    PurchaseCase,
    PurchasePayable,
    User,
)
from app.schemas.common import (
    PayableOut,
    PayableUpdate,
    PurchaseCreate,
)
from app.services.payables import (
    apply_payment_condition,
    normalize_condition,
    payable_balance,
    refresh_payable,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _payable_due_date(purchase: PurchaseCase) -> datetime:
    base = (
        _as_utc(purchase.needed_by)
        or _as_utc(purchase.document_date)
        or _as_utc(purchase.created_at)
        or datetime.now(UTC)
    )
    return base + timedelta(days=PAYABLE_TERM_DAYS)


def _received_value(purchase: PurchaseCase) -> Decimal:
    total = Decimal("0")
    for item in purchase.items:
        net = Decimal(item.received_quantity) - Decimal(item.returned_quantity)
        if net > 0:
            total += net * Decimal(item.unit_cost)
    return total.quantize(Decimal("0.01"))


def _active_payable(purchase: PurchaseCase) -> PurchasePayable | None:
    for payable in purchase.payables:
        if payable.status != "cancelled":
            return payable
    return None


def _owed_value(purchase: PurchaseCase) -> Decimal:
    """Valor devido ao fornecedor.

    P9/P12: a compra de peças deve o valor acordado na cotação vencedora desde a aprovação.
    Quando o saldo pendente é encerrado, o fornecedor não entrega o restante e o título
    passa a valer o que foi efetivamente recebido.
    """
    if purchase.purchase_type == "expense":
        return Decimal(purchase.expense_amount or 0)
    if purchase.status == "closed":
        return _received_value(purchase)
    quote = next(
        (entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None
    )
    if quote is not None:
        return Decimal(quote.total).quantize(Decimal("0.01"))
    return _received_value(purchase)


def _payable_condition(purchase: PurchaseCase) -> tuple[str, int, int, int]:
    """Condição combinada: a da cotação vencedora; sem ela, à vista no prazo padrão."""
    quote = next(
        (entry for entry in purchase.quotes if entry.id == purchase.selected_quote_id), None
    )
    if quote is not None:
        return (
            quote.payment_type,
            quote.installment_count,
            quote.first_due_days,
            quote.interval_days,
        )
    default_first_due = 0 if purchase.purchase_type == "expense" else PAYABLE_TERM_DAYS
    return "cash", 1, default_first_due, PAYABLE_TERM_DAYS


def _payable_base_date(purchase: PurchaseCase, payable: PurchasePayable | None) -> datetime:
    """P12: data base é a data do documento da compra e, sem ela, a data da aprovação."""
    return (
        _as_utc(purchase.document_date)
        or _as_utc(payable.created_at if payable else None)
        or datetime.now(UTC)
    )


def _apply_payable_condition(
    purchase: PurchaseCase,
    payable: PurchasePayable,
    *,
    condition: tuple[str, int, int, int] | None = None,
) -> None:
    try:
        apply_payment_condition(
            payable,
            base_date=_payable_base_date(purchase, payable),
            condition=condition,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _sync_payable(
    db: Session,
    purchase: PurchaseCase,
    *,
    reason: str | None = None,
    condition: tuple[str, int, int, int] | None = None,
) -> PurchasePayable | None:
    """Keep the accounts payable title aligned with what the purchase actually owes."""
    amount = _owed_value(purchase)
    payable = _active_payable(purchase)
    if purchase.status == "cancelled":
        if payable and payable.status != "cancelled":
            payable.status = "cancelled"
            payable.cancelled_at = datetime.now(UTC)
            payable.cancel_reason = (reason or purchase.cancel_reason or "")[:255] or None
            _event(
                db,
                purchase,
                "payable_cancelled",
                f"Título a pagar de {payable.amount:.2f} encerrado com o cancelamento.",
            )
        return payable
    if amount <= 0:
        if payable and payable.status in {"open", "partial"} and not payable.payments:
            payable.status = "cancelled"
            payable.cancelled_at = datetime.now(UTC)
            payable.cancel_reason = "Sem valor a pagar depois do encerramento do saldo."
            _event(
                db,
                purchase,
                "payable_cancelled",
                "Título a pagar encerrado por não haver valor recebido.",
            )
        elif payable:
            refresh_payable(payable)
        return payable
    if payable:
        if Decimal(payable.amount) != amount and payable.status in {"open", "partial"}:
            payable.amount = amount
            _apply_payable_condition(purchase, payable)
        elif not payable.installments:
            _apply_payable_condition(purchase, payable, condition=_payable_condition(purchase))
        refresh_payable(payable)
        return payable
    payable = PurchasePayable(
        supplier_id=purchase.supplier_id,
        supplier_name=purchase.supplier_name
        or (purchase.supplier.name if purchase.supplier else None),
        amount=amount,
        due_date=_payable_due_date(purchase),
        status="open",
    )
    purchase.payables.append(payable)
    db.flush()
    _apply_payable_condition(
        purchase,
        payable,
        condition=normalize_condition(*(condition or _payable_condition(purchase))),
    )
    _event(db, purchase, "payable_created", f"Título a pagar de {amount:.2f} criado.")
    return payable


def _pay_purchase_now(
    db: Session,
    purchase: PurchaseCase,
    payload: PurchaseCreate,
    user: User,
) -> None:
    """Compra de marketplace paga no checkout: o título já nasce baixado."""
    amount = (
        Decimal(purchase.expense_amount or 0)
        if purchase.purchase_type == "expense"
        else _purchase_total(purchase)
    )
    if amount <= 0:
        return
    payable = _active_payable(purchase)
    if payable is None:
        payable = PurchasePayable(
            supplier_id=purchase.supplier_id,
            supplier_name=purchase.supplier_name
            or (purchase.supplier.name if purchase.supplier else None),
            amount=amount,
            due_date=_payable_due_date(purchase),
            status="open",
        )
        purchase.payables.append(payable)
        db.flush()
    payment = PayablePayment(
        payable_id=payable.id,
        amount=Decimal(payable.amount),
        paid_at=_as_utc(payload.paid_date) or datetime.now(UTC),
        method=(payload.paid_method or "").strip() or None,
        notes="Pago no checkout da plataforma.",
        created_by_id=user.id,
    )
    payable.payments.append(payment)
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        purchase,
        "payable_settled",
        f"Título a pagar de {Decimal(payable.amount):.2f} quitado no checkout por "
        f"{user.full_name}.",
        user=user,
    )


def _payable_with_payments(purchase: PurchaseCase) -> PurchasePayable | None:
    for payable in purchase.payables:
        if payable.status != "cancelled" and payable.payments:
            return payable
    return None


def _find_payable(purchase: PurchaseCase, payable_id: str) -> PurchasePayable:
    payable = next((entry for entry in purchase.payables if entry.id == payable_id), None)
    if not payable:
        raise HTTPException(status_code=404, detail="Título a pagar não encontrado nesta compra.")
    return payable


@router.patch("/{purchase_id}/payables/{payable_id}", response_model=PayableOut)
def update_payable(
    purchase_id: str,
    payable_id: str,
    payload: PayableUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableOut:
    purchase = _load(db, purchase_id, for_update=True)
    payable = _find_payable(purchase, payable_id)
    if payable.status != "open":
        raise HTTPException(
            status_code=409, detail="Somente títulos em aberto podem ser ajustados."
        )
    for field, value in payload.model_dump(exclude_unset=True, exclude={"paid_at"}).items():
        if value is not None:
            setattr(payable, field, value)
    _event(db, purchase, "payable_updated", f"Título a pagar ajustado por {user.full_name}.")
    db.commit()
    return PayableOut.model_validate(_find_payable(_load(db, purchase.id), payable_id))


@router.post("/{purchase_id}/payables/{payable_id}/settle", response_model=PayableOut)
def settle_payable(
    purchase_id: str,
    payable_id: str,
    payload: PayableUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableOut:
    purchase = _load(db, purchase_id, for_update=True)
    payable = _find_payable(purchase, payable_id)
    if payable.status == "cancelled":
        raise HTTPException(status_code=409, detail="Este título foi encerrado com o cancelamento.")
    balance = payable_balance(payable)
    if balance <= 0:
        raise HTTPException(status_code=409, detail="Este título já está pago.")
    payment = PayablePayment(
        payable_id=payable.id,
        amount=balance,
        paid_at=_as_utc(payload.paid_at) or datetime.now(UTC),
        method=(payload.payment_method or "").strip() or None,
        notes=(payload.payment_notes or "").strip() or None,
        created_by_id=user.id,
    )
    db.add(payment)
    payable.payments.append(payment)
    payable.paid_at = payment.paid_at
    if payment.method:
        payable.payment_method = payment.method
    if payment.notes:
        payable.payment_notes = payment.notes
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        purchase,
        "payable_settled",
        f"Título a pagar de {Decimal(payment.amount):.2f} quitado por {user.full_name}.",
        user=user,
    )
    db.commit()
    return PayableOut.model_validate(_find_payable(_load(db, purchase.id), payable_id))
