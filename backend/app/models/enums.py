import enum

from app.models.telemetry import HealthSnapshot, TelemetryEvent  # noqa: F401  (reexportado)


class UserRole(enum.StrEnum):
    admin = "admin"
    manager = "manager"
    operator = "operator"
    stock = "stock"
    finance = "finance"
    viewer = "viewer"


class InvoiceStatus(enum.StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    cancelled = "cancelled"


class InvoiceSource(enum.StrEnum):
    manual = "manual"
    mercadolivre = "mercadolivre"
    shopee = "shopee"


class MovementType(enum.StrEnum):
    sale = "sale"
    cancellation = "cancellation"
    adjustment = "adjustment"
    purchase_received = "purchase_received"
    customer_return = "customer_return"
