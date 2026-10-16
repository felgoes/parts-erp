"""Accounts payable module: consolidated view, partial settlement, aging and reports."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import payables_actions, payables_reading, payables_support
from app.api.routes.payables_actions import (  # noqa: F401
    create_payment,
    delete_payment,
    get_payable,
    reconcile_payment,
    update_payable,
)
from app.api.routes.payables_reading import (  # noqa: F401
    export_payables,
    list_payables,
    payables_report,
)
from app.api.routes.payables_support import (  # noqa: F401  # noqa: F401
    AGING_LABELS,
    SAO_PAULO,
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

# Os módulos por assunto já trazem o prefixo: aqui não entra outro, senão as rotas saem em
# /payables/payables (foi o que aconteceu na divisão de 12/10 e a tela ficou em 404).
router = APIRouter()

router.include_router(payables_support.router)
router.include_router(payables_reading.router)
router.include_router(payables_actions.router)
