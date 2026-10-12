"""Accounts payable module: consolidated view, partial settlement, aging and reports."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.payables_support import (  # noqa: F401
    _aging,
    _all_payables,
    _as_utc,
    _condition_requested,
    _day,
    _day_end,
    _day_start,
    _days_overdue,
    _days_until_due,
    _detail,
    _due_day,
    _event,
    _filtered,
    _installment_out,
    _is_open,
    _item,
    _load,
    _payment_day,
    _summary,
    _today,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    PayablePayment,
    User,
)
from app.schemas.common import (
    PayableDetailOut,
    PayablePaymentCreate,
    PayableReconcile,
    PayableUpdate,
)
from app.services.payables import (
    apply_payment_condition,
    installment_balance,
    normalize_condition,
    payable_balance,
    refresh_payable,
)

router = APIRouter(prefix="/payables", tags=["Contas a pagar"])


@router.get("/{payable_id}", response_model=PayableDetailOut)
def get_payable(
    payable_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.FINANCE_READ)),
) -> PayableDetailOut:
    payable = _load(db, payable_id)
    return _detail(payable)


@router.patch("/{payable_id}", response_model=PayableDetailOut)
def update_payable(
    payable_id: str,
    payload: PayableUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableDetailOut:
    payable = _load(db, payable_id)
    if payable.status == "cancelled":
        raise HTTPException(
            status_code=409, detail="Título encerrado com o cancelamento da compra."
        )
    if payload.due_date is not None:
        payable.due_date = _as_utc(payload.due_date)
    if payload.payment_method:
        payable.payment_method = payload.payment_method
    if payload.payment_notes:
        payable.payment_notes = payload.payment_notes
    if _condition_requested(payload):
        # P12: mudar a condição recalcula apenas as parcelas em aberto; parcela paga não muda.
        # Os novos vencimentos contam a partir de hoje, para o acordo novo não nascer vencido.
        try:
            condition = normalize_condition(
                payload.payment_type or payable.payment_type,
                payload.installment_count
                if payload.installment_count is not None
                else payable.installment_count,
                payload.first_due_days
                if payload.first_due_days is not None
                else payable.first_due_days,
                payload.interval_days
                if payload.interval_days is not None
                else payable.interval_days,
            )
            apply_payment_condition(payable, base_date=datetime.now(UTC), condition=condition)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        refresh_payable(payable)
        _event(
            db,
            payable.purchase,
            "payable_terms_updated",
            f"Condição de pagamento alterada para {payable.payment_terms} por {user.full_name}. "
            "Parcelas em aberto foram recalculadas.",
            user,
        )
    else:
        _event(
            db,
            payable.purchase,
            "payable_updated",
            f"Vencimento do título ajustado por {user.full_name}.",
            user,
        )
    db.commit()
    payable = _load(db, payable_id)
    return _detail(payable)


@router.post("/{payable_id}/payments", response_model=PayableDetailOut)
def create_payment(
    payable_id: str,
    payload: PayablePaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableDetailOut:
    payable = _load(db, payable_id)
    if payable.status == "cancelled":
        raise HTTPException(
            status_code=409, detail="Título encerrado com o cancelamento da compra."
        )
    if payload.idempotency_key:
        existing = next(
            (
                payment
                for payment in payable.payments
                if payment.idempotency_key == payload.idempotency_key
            ),
            None,
        )
        if existing:
            return _detail(payable)
    balance = payable_balance(payable)
    amount = Decimal(payload.amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Informe um valor de pagamento maior que zero.")
    if amount > balance:
        raise HTTPException(
            status_code=422,
            detail=f"O saldo em aberto deste título é {balance:.2f}.",
        )
    installment = None
    if payload.installment_id:
        installment = next(
            (entry for entry in payable.installments if entry.id == payload.installment_id), None
        )
        if not installment:
            raise HTTPException(status_code=404, detail="Parcela não encontrada neste título.")
        installment_open = installment_balance(installment)
        if amount > installment_open:
            raise HTTPException(
                status_code=422,
                detail=f"O saldo desta parcela é {installment_open:.2f}.",
            )
    payment = PayablePayment(
        payable_id=payable.id,
        installment=installment,
        amount=amount,
        paid_at=_as_utc(payload.paid_at) or datetime.now(UTC),
        method=(payload.method or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        idempotency_key=payload.idempotency_key,
        created_by_id=user.id,
    )
    db.add(payment)
    payable.payments.append(payment)
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        payable.purchase,
        "payable_payment",
        f"Pagamento de {amount:.2f} registrado por {user.full_name}"
        + (f" · {payment.method}" if payment.method else "")
        + f". Saldo: {payable_balance(payable):.2f}.",
        user,
    )
    db.commit()
    payable = _load(db, payable_id)
    return _detail(payable)


@router.delete("/{payable_id}/payments/{payment_id}", response_model=PayableDetailOut)
def delete_payment(
    payable_id: str,
    payment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableDetailOut:
    payable = _load(db, payable_id)
    payment = next((entry for entry in payable.payments if entry.id == payment_id), None)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado neste título.")
    if payment.reconciled:
        raise HTTPException(
            status_code=409,
            detail="Desfaça a conciliação antes de remover este pagamento.",
        )
    amount = Decimal(payment.amount)
    payable.payments.remove(payment)
    db.flush()
    refresh_payable(payable)
    _event(
        db,
        payable.purchase,
        "payable_payment_removed",
        f"Pagamento de {amount:.2f} removido por {user.full_name}. "
        f"Saldo: {payable_balance(payable):.2f}.",
        user,
    )
    db.commit()
    payable = _load(db, payable_id)
    return _detail(payable)


@router.post("/{payable_id}/payments/{payment_id}/reconcile", response_model=PayableDetailOut)
def reconcile_payment(
    payable_id: str,
    payment_id: str,
    payload: PayableReconcile,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PayableDetailOut:
    payable = _load(db, payable_id)
    payment = next((entry for entry in payable.payments if entry.id == payment_id), None)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado neste título.")
    payment.reconciled = payload.reconciled
    payment.reconciled_at = datetime.now(UTC) if payload.reconciled else None
    payment.reconciled_by_id = user.id if payload.reconciled else None
    _event(
        db,
        payable.purchase,
        "payable_reconciled" if payload.reconciled else "payable_reconciliation_undone",
        (
            f"Pagamento de {Decimal(payment.amount):.2f} conciliado por {user.full_name}."
            if payload.reconciled
            else (
                f"Conciliação do pagamento de {Decimal(payment.amount):.2f} desfeita por "
                f"{user.full_name}."
            )
        ),
        user,
    )
    db.commit()
    payable = _load(db, payable_id)
    return _detail(payable)
