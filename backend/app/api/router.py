from fastapi import APIRouter

from app.api.routes import auth, catalog, customers, dashboard, integrations, invoices, products, telemetry, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(products.router)
api_router.include_router(catalog.router)
api_router.include_router(telemetry.router)
api_router.include_router(customers.router)
api_router.include_router(invoices.router)
api_router.include_router(integrations.router)
api_router.include_router(integrations.shopee_router)
