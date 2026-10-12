"""Accounts payable module: consolidated view, partial settlement, aging and reports."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    PayableInstallment,
    PayablePayment,
    PurchaseCase,
    PurchaseEvent,
    PurchasePayable,
    User,
)
from app.schemas.common import (
    PayableAgingBucket,
    PayableDetailOut,
    PayableInstallmentOut,
    PayableListItem,
    PayablePaymentOut,
    PayableSummary,
    PayableUpdate,
)
from app.services.payables import (
    installment_balance,
    installment_paid_total,
    payable_balance,
)

router = APIRouter(prefix="/payables", tags=["Contas a pagar"])


SAO_PAULO = timezone(timedelta(hours=-3))
AGING_LABELS = (
    "A vencer",
    "1 a 15 dias",
    "16 a 30 dias",
    "31 a 60 dias",
    "61 a 90 dias",
    "Mais de 90 dias",
)


def _today() -> date:
    """Operational dates follow America/Sao_Paulo, matching the rest of the ERP."""
    return datetime.now(UTC).astimezone(SAO_PAULO).date()


def _due_day(payable: PurchasePayable) -> date:
    due = payable.due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due.astimezone(SAO_PAULO).date()


def _day(value: date | None) -> date | None:
    return value


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _payment_day(payment: PayablePayment) -> date | None:
    """Payment dates are calendar dates: read them from the stored UTC day, without shifting."""
    moment = _as_utc(payment.paid_at)
    return moment.date() if moment else None


def _event(
    db: Session, purchase: PurchaseCase, event_type: str, detail: str, user: User | None = None
) -> None:
    db.add(
        PurchaseEvent(
            purchase_id=purchase.id,
            user_id=user.id if user else None,
            event_type=event_type,
            detail=detail,
        )
    )


def _load(db: Session, payable_id: str) -> PurchasePayable:
    payable = db.scalar(
        select(PurchasePayable)
        .where(PurchasePayable.id == payable_id)
        .options(
            selectinload(PurchasePayable.payments),
            selectinload(PurchasePayable.installments),
            selectinload(PurchasePayable.purchase),
        )
    )
    if not payable:
        raise HTTPException(status_code=404, detail="Título a pagar não encontrado.")
    return payable


def _all_payables(db: Session) -> list[PurchasePayable]:
    return list(
        db.scalars(
            select(PurchasePayable)
            .options(
                selectinload(PurchasePayable.payments),
                selectinload(PurchasePayable.installments),
                selectinload(PurchasePayable.purchase),
            )
            .order_by(PurchasePayable.due_date.asc())
        )
    )


def _is_open(payable: PurchasePayable) -> bool:
    return payable.status in {"open", "partial"}


def _days_overdue(payable: PurchasePayable) -> int:
    if not _is_open(payable):
        return 0
    return max(0, (_today() - _due_day(payable)).days)


def _days_until_due(payable: PurchasePayable) -> int:
    return (_due_day(payable) - _today()).days


def _item(payable: PurchasePayable) -> PayableListItem:
    purchase = payable.purchase
    payments = list(payable.payments)
    last_payment = max((_as_utc(payment.paid_at) for payment in payments), default=None)
    return PayableListItem(
        id=payable.id,
        purchase_id=purchase.id,
        purchase_number=purchase.number,
        purchase_type=purchase.purchase_type,
        purchase_status=purchase.status,
        expense_category=purchase.expense_category,
        supplier_id=payable.supplier_id,
        supplier_name=payable.supplier_name or purchase.supplier_name,
        amount=Decimal(payable.amount),
        paid_amount=Decimal(payable.paid_amount or 0),
        balance=payable_balance(payable),
        due_date=payable.due_date,
        payment_terms=payable.payment_terms,
        installment_count=len(payable.installments) or 1,
        status=payable.status,
        days_overdue=_days_overdue(payable),
        payment_count=len(payments),
        reconciled_payment_count=sum(1 for payment in payments if payment.reconciled),
        last_payment_at=last_payment,
        created_at=payable.created_at,
    )


def _installment_out(installment: PayableInstallment) -> PayableInstallmentOut:
    return PayableInstallmentOut(
        id=installment.id,
        number=installment.number,
        due_date=installment.due_date,
        amount=Decimal(installment.amount),
        paid_amount=installment_paid_total(installment),
        balance=installment_balance(installment),
    )


def _detail(payable: PurchasePayable) -> PayableDetailOut:
    return PayableDetailOut(
        **_item(payable).model_dump(),
        payment_type=payable.payment_type,
        first_due_days=payable.first_due_days,
        interval_days=payable.interval_days,
        payments=[PayablePaymentOut.model_validate(payment) for payment in payable.payments],
        installments=[_installment_out(installment) for installment in payable.installments],
    )


def _condition_requested(payload: PayableUpdate) -> bool:
    return any(
        getattr(payload, field) is not None
        for field in ("payment_type", "installment_count", "first_due_days", "interval_days")
    )


def _aging(payables: list[PurchasePayable]) -> list[PayableAgingBucket]:
    buckets = {label: {"count": 0, "balance": Decimal("0")} for label in AGING_LABELS}
    for payable in payables:
        if not _is_open(payable):
            continue
        days = _days_until_due(payable)
        if days >= 0:
            label = AGING_LABELS[0]
        else:
            overdue = -days
            if overdue <= 15:
                label = AGING_LABELS[1]
            elif overdue <= 30:
                label = AGING_LABELS[2]
            elif overdue <= 60:
                label = AGING_LABELS[3]
            elif overdue <= 90:
                label = AGING_LABELS[4]
            else:
                label = AGING_LABELS[5]
        buckets[label]["count"] += 1
        buckets[label]["balance"] += payable_balance(payable)
    return [
        PayableAgingBucket(
            label=label, count=values["count"], balance=values["balance"].quantize(Decimal("0.01"))
        )
        for label, values in buckets.items()
    ]


def _filtered(
    payables: list[PurchasePayable],
    *,
    status: str | None,
    supplier: str | None,
    search: str | None,
    due_from: date | None,
    due_to: date | None,
    overdue_only: bool,
) -> list[PurchasePayable]:
    term = (search or "").strip().lower().replace(" ", "")
    supplier_term = (supplier or "").strip().lower().replace(" ", "")
    result: list[PurchasePayable] = []
    for payable in payables:
        purchase = payable.purchase
        if status and payable.status != status:
            continue
        if due_from and _due_day(payable) < due_from:
            continue
        if due_to and _due_day(payable) > due_to:
            continue
        if overdue_only and _days_overdue(payable) == 0:
            continue
        name = (payable.supplier_name or purchase.supplier_name or "").lower()
        if supplier_term and supplier_term not in name.replace(" ", ""):
            continue
        if term:
            haystack = " ".join(
                filter(
                    None,
                    [
                        name,
                        (purchase.number or "").lower(),
                        (purchase.expense_category or "").lower(),
                        (purchase.supplier_order_number or "").lower(),
                    ],
                )
            )
            if term not in haystack.replace(" ", ""):
                continue
        result.append(payable)
    return result


def _summary(
    payables: list[PurchasePayable],
    *,
    next_days: int,
    paid_from: date | None,
    paid_to: date | None,
) -> PayableSummary:
    open_balance = Decimal("0")
    overdue_balance = Decimal("0")
    due_next = Decimal("0")
    paid_in_period = Decimal("0")
    open_count = 0
    overdue_count = 0
    partial_count = 0
    paid_count = 0
    unreconciled = 0
    for payable in payables:
        balance = payable_balance(payable)
        if _is_open(payable):
            open_balance += balance
            open_count += 1
            if payable.status == "partial":
                partial_count += 1
            overdue = _days_overdue(payable)
            if overdue > 0:
                overdue_balance += balance
                overdue_count += 1
            elif _days_until_due(payable) <= next_days:
                due_next += balance
        elif payable.status == "paid":
            paid_count += 1
        for payment in payable.payments:
            if not payment.reconciled:
                unreconciled += 1
            day = _payment_day(payment)
            if (
                day
                and (paid_from is None or day >= paid_from)
                and (paid_to is None or day <= paid_to)
            ):
                paid_in_period += Decimal(payment.amount)
    return PayableSummary(
        open_balance=open_balance.quantize(Decimal("0.01")),
        overdue_balance=overdue_balance.quantize(Decimal("0.01")),
        due_next_days_balance=due_next.quantize(Decimal("0.01")),
        paid_in_period=paid_in_period.quantize(Decimal("0.01")),
        open_count=open_count,
        overdue_count=overdue_count,
        partial_count=partial_count,
        paid_count=paid_count,
        unreconciled_payments=unreconciled,
    )
