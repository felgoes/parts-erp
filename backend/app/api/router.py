from fastapi import APIRouter

from app.api.routes import (
    after_sales,
    auth,
    catalog,
    customers,
    dashboard,
    finance,
    integrations,
    invoices,
    market_studies,
    products,
    purchases,
    telemetry,
    users,
)

api_router = APIRouter()
api_router.include_router(after_sales.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(finance.router)
api_router.include_router(products.router)
api_router.include_router(purchases.router)
api_router.include_router(catalog.router)
api_router.include_router(telemetry.router)
api_router.include_router(customers.router)
api_router.include_router(invoices.router)
api_router.include_router(market_studies.router)
api_router.include_router(integrations.router)
api_router.include_router(integrations.shopee_router)
