from fastapi import APIRouter

from app.api.routes import integrations_mercadolivre, integrations_shopee
from app.api.routes.integrations_mercadolivre import (  # noqa: F401  (reexportado)
    automate_order,
    callback,
    connect,
    get_config,
    order_detail,
    order_history,
    orders,
    request_order_fiscal_document,
    request_order_shipping_label,
    status,
    sync_now,
    update_config,
)
from app.api.routes.integrations_shopee import (  # noqa: F401  (reexportado)
    connect_shopee,
    shopee_callback,
    shopee_config,
    shopee_status,
    update_shopee_config,
)

router = APIRouter()
shopee_router = APIRouter()
router.include_router(integrations_mercadolivre.router)
shopee_router.include_router(integrations_shopee.shopee_router)
