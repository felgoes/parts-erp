from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import Supplier, User
from app.schemas.common import SupplierCreate, SupplierOut

router = APIRouter(prefix="/suppliers", tags=["Fornecedores"])


@router.get("", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> list[SupplierOut]:
    suppliers = db.scalars(select(Supplier).order_by(Supplier.name)).all()
    return [SupplierOut.model_validate(supplier) for supplier in suppliers]


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> SupplierOut:
    """Create a supplier by name; repeating the same name reuses the existing record."""
    name = payload.name.strip()
    existing = db.scalar(select(Supplier).where(Supplier.name == name))
    if existing:
        return SupplierOut.model_validate(existing)
    supplier = Supplier(
        name=name,
        contact=(payload.contact or "").strip() or None,
        document=(payload.document or "").strip() or None,
        default_delivery_days=payload.default_delivery_days,
        default_payment_terms=(payload.default_payment_terms or "").strip() or None,
    )
    db.add(supplier)
    db.commit()
    return SupplierOut.model_validate(supplier)
