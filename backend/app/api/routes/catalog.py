from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Product
from app.schemas.common import CatalogProductOut

router = APIRouter(prefix="/catalog", tags=["Catalogo publico"])


@router.get("/products", response_model=list[CatalogProductOut])
def catalog_products(
    search: str | None = None,
    limit: int = Query(default=48, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[CatalogProductOut]:
    query = select(Product).where(Product.active.is_(True)).order_by(Product.name).limit(limit)
    if search:
        query = query.where(
            or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"))
        )
    products = db.scalars(query)
    return [
        CatalogProductOut(
            id=product.id,
            sku=product.sku,
            name=product.name,
            description=product.description,
            sale_price=product.sale_price,
            in_stock=product.current_stock > 0,
        )
        for product in products
    ]
