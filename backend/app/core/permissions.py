from enum import StrEnum

from app.models import UserRole


class Permission(StrEnum):
    DASHBOARD_READ = "dashboard:read"
    MONITORING_READ = "monitoring:read"
    PRODUCT_READ = "products:read"
    PRODUCT_MANAGE = "products:manage"
    INVENTORY_ADJUST = "inventory:adjust"
    LISTING_MANAGE = "listings:manage"
    PURCHASE_READ = "purchases:read"
    PURCHASE_MANAGE = "purchases:manage"
    PURCHASE_RECEIVE = "purchases:receive"
    INVOICE_READ = "invoices:read"
    INVOICE_CREATE = "invoices:create"
    INVOICE_CONFIRM = "invoices:confirm"
    INVOICE_CANCEL = "invoices:cancel"
    CUSTOMER_READ = "customers:read"
    CUSTOMER_MANAGE = "customers:manage"
    AFTER_SALE_READ = "after-sales:read"
    AFTER_SALE_PROCESS = "after-sales:process"
    AFTER_SALE_CLOSE = "after-sales:close"
    MARKETPLACE_READ = "marketplace:read"
    MARKETPLACE_PROCESS = "marketplace:process"
    INTEGRATION_STATUS = "integrations:status"
    INTEGRATION_CONFIG = "integrations:configure"
    STUDY_READ = "market-studies:read"
    STUDY_RUN = "market-studies:run"
    STUDY_CONFIG = "market-studies:configure"
    FINANCE_READ = "finance:read"
    USERS_MANAGE = "users:manage"
    SETTINGS_MANAGE = "settings:manage"


ALL_PERMISSIONS = frozenset(Permission)
READ_ONLY = frozenset(
    {
        Permission.DASHBOARD_READ,
        Permission.MONITORING_READ,
        Permission.PRODUCT_READ,
        Permission.PURCHASE_READ,
        Permission.INVOICE_READ,
        Permission.CUSTOMER_READ,
        Permission.AFTER_SALE_READ,
        Permission.MARKETPLACE_READ,
        Permission.INTEGRATION_STATUS,
        Permission.STUDY_READ,
        Permission.FINANCE_READ,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.admin: ALL_PERMISSIONS,
    UserRole.manager: ALL_PERMISSIONS
    - {Permission.USERS_MANAGE, Permission.INTEGRATION_CONFIG, Permission.SETTINGS_MANAGE},
    UserRole.operator: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.PRODUCT_READ,
            Permission.INVOICE_READ,
            Permission.INVOICE_CREATE,
            Permission.INVOICE_CONFIRM,
            Permission.CUSTOMER_READ,
            Permission.CUSTOMER_MANAGE,
            Permission.AFTER_SALE_READ,
            Permission.MARKETPLACE_READ,
            Permission.INTEGRATION_STATUS,
        }
    ),
    UserRole.stock: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.PRODUCT_READ,
            Permission.INVENTORY_ADJUST,
            Permission.PURCHASE_READ,
            Permission.PURCHASE_RECEIVE,
            Permission.INVOICE_READ,
            Permission.AFTER_SALE_READ,
            Permission.AFTER_SALE_PROCESS,
            Permission.MARKETPLACE_READ,
            Permission.INTEGRATION_STATUS,
        }
    ),
    UserRole.finance: frozenset(
        {
            Permission.DASHBOARD_READ,
            Permission.PRODUCT_READ,
            Permission.PURCHASE_READ,
            Permission.INVOICE_READ,
            Permission.CUSTOMER_READ,
            Permission.AFTER_SALE_READ,
            Permission.MARKETPLACE_READ,
            Permission.INTEGRATION_STATUS,
            Permission.STUDY_READ,
            Permission.FINANCE_READ,
        }
    ),
    UserRole.viewer: READ_ONLY,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
