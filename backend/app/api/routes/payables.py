"""Accounts payable module: consolidated view, partial settlement, aging and reports."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
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
    PayableListResponse,
    PayableMonthReport,
    PayablePaymentCreate,
    PayablePaymentOut,
    PayableReconcile,
    PayableReportResponse,
    PayableSummary,
    PayableSupplierReport,
    PayableUpdate,
)
from app.services.payables import (
    apply_payment_condition,
    installment_balance,
    installment_paid_total,
    normalize_condition,
    payable_balance,
    refresh_payable,
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
            paid_at = _as_utc(payment.paid_at)
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


@router.get("", response_model=PayableListResponse)
def list_payables(
    status: str | None = Query(default=None, pattern="^(open|partial|paid|cancelled)$"),
    supplier: str | None = None,
    search: str | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    overdue_only: bool = False,
    next_days: int = Query(default=7, ge=1, le=60),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.FINANCE_READ)),
) -> PayableListResponse:
    payables = _all_payables(db)
    filtered = _filtered(
        payables,
        status=status,
        supplier=supplier,
        search=search,
        due_from=due_from,
        due_to=due_to,
        overdue_only=overdue_only,
    )
    window_from = paid_from or due_from
    window_to = paid_to or due_to
    return PayableListResponse(
        items=[_item(payable) for payable in filtered[offset : offset + limit]],
        summary=_summary(filtered, next_days=next_days, paid_from=window_from, paid_to=window_to),
        aging=_aging(filtered),
        next_days=next_days,
    )


@router.get("/report", response_model=PayableReportResponse)
def payables_report(
    due_from: date | None = None,
    due_to: date | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    next_days: int = Query(default=7, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.FINANCE_READ)),
) -> PayableReportResponse:
    payables = _all_payables(db)
    filtered = _filtered(
        payables,
        status=None,
        supplier=None,
        search=None,
        due_from=due_from,
        due_to=due_to,
        overdue_only=False,
    )
    window_from = paid_from or due_from
    window_to = paid_to or due_to
    suppliers: dict[str, dict[str, Decimal | int]] = {}
    months: dict[str, dict[str, Decimal | int]] = {}
    for payable in filtered:
        purchase = payable.purchase
        name = payable.supplier_name or purchase.supplier_name or "Sem fornecedor"
        entry = suppliers.setdefault(
            name, {"open": Decimal("0"), "overdue": Decimal("0"), "paid": Decimal("0"), "titles": 0}
        )
        entry["titles"] = int(entry["titles"]) + 1
        balance = payable_balance(payable)
        if balance > 0:
            entry["open"] = Decimal(entry["open"]) + balance
            if _days_overdue(payable) > 0:
                entry["overdue"] = Decimal(entry["overdue"]) + balance
        for payment in payable.payments:
            paid_at = _as_utc(payment.paid_at)
            day = _payment_day(payment)
            if not day:
                continue
            if (window_from is None or day >= window_from) and (
                window_to is None or day <= window_to
            ):
                entry["paid"] = Decimal(entry["paid"]) + Decimal(payment.amount)
            key = day.strftime("%Y-%m")
            month = months.setdefault(key, {"paid": Decimal("0"), "titles": 0})
            month["paid"] = Decimal(month["paid"]) + Decimal(payment.amount)
            month["titles"] = int(month["titles"]) + 1
    start = due_from or min((_due_day(payable) for payable in filtered), default=_today())
    end = due_to or max((_due_day(payable) for payable in filtered), default=_today())
    label = f"{start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    return PayableReportResponse(
        period_label=label,
        start_date=start,
        end_date=end,
        summary=_summary(filtered, next_days=next_days, paid_from=window_from, paid_to=window_to),
        aging=_aging(filtered),
        by_supplier=[
            PayableSupplierReport(
                supplier_name=name,
                open_balance=Decimal(values["open"]).quantize(Decimal("0.01")),
                overdue_balance=Decimal(values["overdue"]).quantize(Decimal("0.01")),
                paid_in_period=Decimal(values["paid"]).quantize(Decimal("0.01")),
                titles=int(values["titles"]),
            )
            for name, values in sorted(
                suppliers.items(), key=lambda entry: -Decimal(entry[1]["open"])
            )
        ],
        by_month=[
            PayableMonthReport(
                month=month,
                paid=Decimal(values["paid"]).quantize(Decimal("0.01")),
                titles=int(values["titles"]),
            )
            for month, values in sorted(months.items())
        ],
    )


@router.get("/export.csv")
def export_payables(
    status: str | None = Query(default=None, pattern="^(open|partial|paid|cancelled)$"),
    supplier: str | None = None,
    search: str | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.FINANCE_READ)),
) -> Response:
    payables = _filtered(
        _all_payables(db),
        status=status,
        supplier=supplier,
        search=search,
        due_from=due_from,
        due_to=due_to,
        overdue_only=overdue_only,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            "Vencimento",
            "Status",
            "Fornecedor",
            "Origem",
            "Numero",
            "Categoria",
            "Valor",
            "Pago",
            "Saldo",
            "Dias em atraso",
            "Pagamentos",
            "Conciliados",
            "Ultimo pagamento",
        ]
    )
    for payable in payables:
        item = _item(payable)
        writer.writerow(
            [
                _due_day(payable).strftime("%d/%m/%Y"),
                item.status,
                item.supplier_name or "",
                "Despesa" if item.purchase_type == "expense" else "Compra",
                item.purchase_number,
                item.expense_category or "",
                f"{item.amount:.2f}".replace(".", ","),
                f"{item.paid_amount:.2f}".replace(".", ","),
                f"{item.balance:.2f}".replace(".", ","),
                item.days_overdue,
                item.payment_count,
                item.reconciled_payment_count,
                item.last_payment_at.strftime("%d/%m/%Y") if item.last_payment_at else "",
            ]
        )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contas-a-pagar.csv"'},
    )


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
        f"Pagamento de {amount:.2f} removido por {user.full_name}. Saldo: {payable_balance(payable):.2f}.",
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
            else f"Conciliação do pagamento de {Decimal(payment.amount):.2f} desfeita por {user.full_name}."
        ),
        user,
    )
    db.commit()
    payable = _load(db, payable_id)
    return _detail(payable)
