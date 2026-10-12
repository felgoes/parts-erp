"""Accounts payable module: consolidated view, partial settlement, aging and reports."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
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
    User,
)
from app.schemas.common import (
    PayableListResponse,
    PayableMonthReport,
    PayableReportResponse,
    PayableSupplierReport,
)
from app.services.payables import (
    payable_balance,
)

router = APIRouter(prefix="/payables", tags=["Contas a pagar"])


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
