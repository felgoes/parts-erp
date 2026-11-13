from fastapi import APIRouter

from app.api.routes.integrations_mercadolivre_full_common import _delta, _serialize_shipment
from app.api.routes.integrations_mercadolivre_full_inventory import router as inventory_router
from app.api.routes.integrations_mercadolivre_full_shipments import router as shipments_router

router = APIRouter(prefix="/integrations/mercadolivre/full", tags=["Mercado Livre Full"])
router.include_router(inventory_router)
router.include_router(shipments_router)
