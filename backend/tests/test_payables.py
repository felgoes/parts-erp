from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.payables import (
    create_payment,
    delete_payment,
    export_payables,
    get_payable,
    list_payables,
    payables_report,
    reconcile_payment,
    update_payable,
)
from app.api.routes.purchases import create_purchase
from app.models import PayablePayment, PurchasePayable
from app.schemas.common import (
    PayablePaymentCreate,
    PayableReconcile,
    PayableUpdate,
    PurchaseCreate,
)


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id="user-finance", full_name="Financeiro QA")


def _expense(db: Session, user: SimpleNamespace, amount: str, supplier: str = "Fornecedor AP", due_in_days: int = 10):
    expense = create_purchase(
        PurchaseCreate(
            purchase_type="expense",
            expense_category="Serviços",
            expense_amount=Decimal(amount),
            supplier_name=supplier,
            needed_by=datetime.now(UTC) + timedelta(days=due_in_days - 30),
        ),
        db,
        user,
    )
    return expense.payables[0]


def _list(db: Session, user: SimpleNamespace, **overrides):
    params = {
        "status": None,
        "supplier": None,
        "search": None,
        "due_from": None,
        "due_to": None,
        "paid_from": None,
        "paid_to": None,
        "overdue_only": False,
        "next_days": 7,
        "limit": 200,
        "offset": 0,
    }
    params.update(overrides)
    return list_payables(**params, db=db, _=user)


def test_partial_payments_settle_the_title_and_are_idempotent(db: Session) -> None:
    user = _actor()
    payable = _expense(db, user, "500.00")
    assert payable.status == "open"
    assert payable.amount == Decimal("500.00")

    partial = create_payment(payable.id, PayablePaymentCreate(amount=Decimal("200.00"), method="Pix"), db, user)
    assert partial.status == "partial"
    assert partial.paid_amount == Decimal("200.00")
    assert partial.balance == Decimal("300.00")
    assert len(partial.payments) == 1

    settled = create_payment(
        payable.id,
        PayablePaymentCreate(amount=Decimal("300.00"), idempotency_key="qa-payment-key-0001"),
        db,
        user,
    )
    assert settled.status == "paid"
    assert settled.balance == Decimal("0.00")

    # Reenviar o mesmo recibo não duplica o pagamento.
    repeated = create_payment(
        payable.id,
        PayablePaymentCreate(amount=Decimal("300.00"), idempotency_key="qa-payment-key-0001"),
        db,
        user,
    )
    assert len(repeated.payments) == 2
    assert db.scalar(select(func.count(PayablePayment.id))) == 2

    with pytest.raises(HTTPException) as error:
        create_payment(payable.id, PayablePaymentCreate(amount=Decimal("10.00")), db, user)
    assert error.value.status_code == 422


def test_reconciliation_protects_the_payment_and_removal_restores_the_balance(db: Session) -> None:
    user = _actor()
    payable = _expense(db, user, "150.00")
    paid = create_payment(payable.id, PayablePaymentCreate(amount=Decimal("150.00")), db, user)
    payment_id = paid.payments[0].id

    reconciled = reconcile_payment(payable.id, payment_id, PayableReconcile(reconciled=True), db, user)
    assert reconciled.payments[0].reconciled is True
    assert reconciled.reconciled_payment_count == 1

    with pytest.raises(HTTPException) as error:
        delete_payment(payable.id, payment_id, db, user)
    assert error.value.status_code == 409

    reconcile_payment(payable.id, payment_id, PayableReconcile(reconciled=False), db, user)
    restored = delete_payment(payable.id, payment_id, db, user)

    assert restored.status == "open"
    assert restored.balance == Decimal("150.00")
    assert restored.payments == []


def test_list_summary_aging_and_filters(db: Session) -> None:
    user = _actor()
    overdue = _expense(db, user, "100.00", supplier="Fornecedor Vencido", due_in_days=10)
    upcoming = _expense(db, user, "50.00", supplier="Fornecedor A Vencer", due_in_days=32)
    paid = _expense(db, user, "80.00", supplier="Fornecedor Pago", due_in_days=12)
    create_payment(paid.id, PayablePaymentCreate(amount=Decimal("80.00"), method="Boleto"), db, user)
    update_payable(
        overdue.id,
        PayableUpdate(due_date=datetime.now(UTC) - timedelta(days=40)),
        db,
        user,
    )

    listing = _list(db, user)
    assert {item.supplier_name for item in listing.items} == {
        "Fornecedor Vencido",
        "Fornecedor A Vencer",
        "Fornecedor Pago",
    }
    assert listing.summary.open_count == 2
    assert listing.summary.overdue_count == 1
    assert listing.summary.open_balance == Decimal("150.00")
    assert listing.summary.overdue_balance == Decimal("100.00")
    assert listing.summary.paid_in_period == Decimal("80.00")
    assert listing.summary.unreconciled_payments == 1

    buckets = {bucket.label: bucket for bucket in listing.aging}
    assert buckets["A vencer"].balance == Decimal("50.00")
    assert buckets["31 a 60 dias"].balance == Decimal("100.00")

    overdue_only = _list(db, user, overdue_only=True)
    assert [item.supplier_name for item in overdue_only.items] == ["Fornecedor Vencido"]
    assert overdue_only.items[0].days_overdue >= 39

    by_supplier = _list(db, user, supplier="avencer")
    assert [item.supplier_name for item in by_supplier.items] == ["Fornecedor A Vencer"]

    remaining = _list(db, user, status="open")
    assert {item.supplier_name for item in remaining.items} == {"Fornecedor Vencido", "Fornecedor A Vencer"}


def test_report_groups_by_supplier_and_month(db: Session) -> None:
    user = _actor()
    first = _expense(db, user, "120.00", supplier="Fornecedor Relatório")
    second = _expense(db, user, "30.00", supplier="Fornecedor Relatório")
    create_payment(first.id, PayablePaymentCreate(amount=Decimal("60.00")), db, user)
    create_payment(second.id, PayablePaymentCreate(amount=Decimal("30.00")), db, user)

    report = payables_report(
        due_from=None,
        due_to=None,
        paid_from=None,
        paid_to=None,
        next_days=7,
        db=db,
        _=user,
    )

    supplier = next(entry for entry in report.by_supplier if entry.supplier_name == "Fornecedor Relatório")
    assert supplier.titles == 2
    assert supplier.paid_in_period == Decimal("90.00")
    assert supplier.open_balance == Decimal("60.00")
    assert report.summary.paid_in_period == Decimal("90.00")
    assert report.by_month and report.by_month[0].paid == Decimal("90.00")


def test_csv_export_and_detail_keep_the_history(db: Session) -> None:
    user = _actor()
    payable = _expense(db, user, "45.50", supplier="Fornecedor CSV")
    create_payment(payable.id, PayablePaymentCreate(amount=Decimal("20.00"), method="Dinheiro"), db, user)

    detail = get_payable(payable.id, db, user)
    assert detail.payments[0].method == "Dinheiro"
    assert detail.balance == Decimal("25.50")

    response = export_payables(
        status=None,
        supplier=None,
        search=None,
        due_from=None,
        due_to=None,
        overdue_only=False,
        db=db,
        _=user,
    )
    body = response.body.decode("utf-8")
    assert "Fornecedor CSV" in body
    assert "25,50" in body


def test_cancelled_title_rejects_new_payments(db: Session) -> None:
    user = _actor()
    payable = _expense(db, user, "70.00")
    stored = db.get(PurchasePayable, payable.id)
    stored.status = "cancelled"
    db.commit()

    with pytest.raises(HTTPException) as error:
        create_payment(payable.id, PayablePaymentCreate(amount=Decimal("10.00")), db, user)
    assert error.value.status_code == 409
