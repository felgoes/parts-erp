from fastapi import APIRouter

from app.api.routes import (
    purchases_creation,
    purchases_import,
    purchases_items,
    purchases_lifecycle,
    purchases_payables,
    purchases_quotes,
    purchases_receiving,
    purchases_support,
)
from app.api.routes.purchases_creation import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    _find_duplicate_purchase,
    _register_import_document,
    create_purchase,
)
from app.api.routes.purchases_import import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    confirm_imported_purchase,
    import_document_duplicates,
    import_purchase_document,
)
from app.api.routes.purchases_items import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    add_purchase_item,
    download_purchase_attachment,
    get_purchase,
    remove_purchase_item,
    update_purchase_item,
    upload_purchase_attachments,
)
from app.api.routes.purchases_lifecycle import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    _delete_blockers,
    _deletion_effects,
    _received_pending_return,
    cancel_purchase,
    close_purchase_balance,
    delete_purchase,
    update_purchase,
)
from app.api.routes.purchases_payables import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    _active_payable,
    _apply_payable_condition,
    _find_payable,
    _owed_value,
    _pay_purchase_now,
    _payable_base_date,
    _payable_condition,
    _payable_due_date,
    _payable_with_payments,
    _received_value,
    _sync_payable,
    settle_payable,
    update_payable,
)
from app.api.routes.purchases_quotes import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    add_quote,
    place_order,
    select_quote,
)
from app.api.routes.purchases_receiving import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    _apply_receipt,
    _pending_return,
    _register_returns,
    receive_purchase,
    receive_purchase_in_full,
)
from app.api.routes.purchases_support import (  # noqa: F401  (reexportado para o resto do app e para os testes)
    PAYABLE_TERM_DAYS,
    _apply_supplier_defaults,
    _as_utc,
    _event,
    _load,
    _mask_costs,
    _present,
    _purchase_total,
    _recompute_purchase_costs,
)

router = APIRouter()

router.include_router(purchases_support.router)
router.include_router(purchases_payables.router)
router.include_router(purchases_receiving.router)
router.include_router(purchases_lifecycle.router)
router.include_router(purchases_creation.router)
router.include_router(purchases_items.router)
router.include_router(purchases_quotes.router)
router.include_router(purchases_import.router)
