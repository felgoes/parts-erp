import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import MovementType, Product, StockMovement, User, UserRole
from app.schemas.common import ProductCreate, ProductOut, ProductUpdate, StockAdjustment, StockMovementOut
from app.services.stock import move_stock

router = APIRouter(prefix="/products", tags=["Produtos"])


@router.get("", response_model=list[ProductOut])
def list_products(
    search: str | None = None,
    low_stock: bool = False,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Product]:
    query = select(Product).order_by(Product.name).limit(limit)
    if search:
        query = query.where(
            or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"))
        )
    if low_stock:
        query = query.where(Product.current_stock <= Product.minimum_stock)
    return list(db.scalars(query))


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Product:
    product = Product(**payload.model_dump(exclude={"current_stock"}), current_stock=0)
    db.add(product)
    try:
        db.flush()
        if payload.current_stock:
            move_stock(
                db,
                product_id=product.id,
                quantity=payload.current_stock,
                movement_type=MovementType.adjustment,
                reason="Saldo inicial",
                reference=None,
                idempotency_key=f"initial:{product.id}",
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU já cadastrado") from exc
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/adjust-stock", response_model=ProductOut)
def adjust_stock(
    product_id: str,
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Product:
    move_stock(
        db,
        product_id=product_id,
        quantity=payload.quantity,
        movement_type=MovementType.adjustment,
        reason=payload.reason,
        reference=None,
        idempotency_key=f"adjustment:{secrets.token_urlsafe(18)}",
    )
    db.commit()
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


@router.get("/{product_id}/movements", response_model=list[StockMovementOut])
def product_movements(
    product_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[StockMovement]:
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc())
            .limit(100)
        )
    )
