import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.models import (
    MovementType,
    Product,
    ProductMarketplaceListing,
    StockMovement,
    User,
)
from app.schemas.common import (
    ProductChannelDraftIn,
    ProductChannelMetadataOut,
    ProductCreate,
    ProductDetailOut,
    ProductOut,
    ProductUpdate,
    StockAdjustment,
    StockMovementOut,
)
from app.services.product_channels import (
    channel_metadata,
    publish_channel_listing,
    save_channel_draft,
)
from app.services.product_media import MAX_IMAGE_BYTES, product_image_path, store_product_image
from app.services.stock import move_stock

router = APIRouter(prefix="/products", tags=["Produtos"])


@router.get("/channel-metadata/{provider}", response_model=ProductChannelMetadataOut)
def get_channel_metadata(
    provider: str,
    query: str | None = Query(default=None, max_length=200),
    category_id: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LISTING_MANAGE)),
) -> dict:
    try:
        return channel_metadata(db, provider, query=query, category_id=category_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Não foi possível consultar os requisitos do canal ({provider})",
        ) from exc


@router.put("/{product_id}/channels/{provider}/draft", response_model=ProductDetailOut)
def update_channel_draft(
    product_id: str,
    provider: str,
    payload: ProductChannelDraftIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    try:
        save_channel_draft(db, product, provider, payload)
        db.commit()
        db.refresh(product)
        return product
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{product_id}/channels/{provider}/publish", response_model=ProductDetailOut)
def publish_product_channel(
    product_id: str,
    provider: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    listing = db.scalar(
        select(ProductMarketplaceListing)
        .where(
            ProductMarketplaceListing.product_id == product_id,
            ProductMarketplaceListing.provider == provider,
        )
        .order_by(ProductMarketplaceListing.external_item_id.is_not(None).desc())
        .limit(1)
    )
    if not listing or not listing.channel_data:
        raise HTTPException(status_code=409, detail="Salve os dados do canal antes de sincronizar")
    try:
        publish_channel_listing(db, product, listing)
        db.refresh(product)
        return product
    except ValueError as exc:
        listing.sync_status = "blocked"
        listing.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=(
                f"Falha ao sincronizar com {provider}. Confira o anúncio na plataforma "
                "antes de tentar novamente."
            ),
        ) from exc


@router.get("", response_model=list[ProductOut])
def list_products(
    search: str | None = None,
    low_stock: bool = False,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRODUCT_READ)),
) -> list[ProductOut]:
    query = select(Product).order_by(Product.name).limit(limit)
    if search:
        query = query.where(
            or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"))
        )
    if low_stock:
        query = query.where(Product.current_stock <= Product.minimum_stock)
    products = list(db.scalars(query))
    if has_permission(actor.role, Permission.FINANCE_READ):
        return products
    return [
        ProductOut.model_validate(product).model_copy(update={"cost_price": None})
        for product in products
    ]


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
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
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/images", response_model=ProductOut)
def upload_product_images(
    product_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if not files or len(files) > 8:
        raise HTTPException(status_code=422, detail="Envie de 1 a 8 fotos por vez")
    if len(product.images or []) + len(files) > 20:
        raise HTTPException(status_code=422, detail="O cadastro aceita até 20 fotos")
    saved_files: list[Path] = []
    images = list(product.images or [])
    try:
        for upload in files:
            content = upload.file.read(MAX_IMAGE_BYTES + 1)
            filename, width, height = store_product_image(content)
            saved_files.append(product_image_path(filename))
            image_id = secrets.token_hex(12)
            images.append(
                {
                    "id": image_id,
                    "filename": filename,
                    "url": f"/api/v1/catalog/images/{filename}",
                    "position": len(images),
                    "width": width,
                    "height": height,
                    "uploaded_at": datetime.now(UTC).isoformat(),
                }
            )
        product.images = images
        db.commit()
        db.refresh(product)
        return product
    except ValueError as exc:
        for path in saved_files:
            path.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        for path in saved_files:
            path.unlink(missing_ok=True)
        db.rollback()
        raise
    finally:
        for upload in files:
            upload.file.close()


@router.delete("/{product_id}/images/{image_id}", response_model=ProductOut)
def delete_product_image(
    product_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PRODUCT_MANAGE)),
) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    images = list(product.images or [])
    image = next((row for row in images if row.get("id") == image_id), None)
    if not image:
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    product.images = [
        {**row, "position": index}
        for index, row in enumerate(row for row in images if row.get("id") != image_id)
    ]
    db.commit()
    filename = image.get("filename")
    if filename:
        try:
            product_image_path(filename).unlink(missing_ok=True)
        except ValueError:
            pass
    db.refresh(product)
    return product


@router.get("/{product_id}/detail", response_model=ProductDetailOut)
def product_detail(
    product_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRODUCT_READ)),
) -> ProductDetailOut:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if has_permission(actor.role, Permission.FINANCE_READ):
        return product
    return ProductDetailOut.model_validate(product).model_copy(update={"cost_price": None})


@router.post("/{product_id}/adjust-stock", response_model=ProductOut)
def adjust_stock(
    product_id: str,
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.INVENTORY_ADJUST)),
) -> ProductOut:
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
    try:
        from app.services.product_channels import sync_product_stock_all

        sync_product_stock_all(db, product)
    except Exception:
        # O saldo local permanece registrado; a sincronização será tentada no próximo ciclo.
        db.rollback()
    if has_permission(actor.role, Permission.FINANCE_READ):
        return product
    return ProductOut.model_validate(product).model_copy(update={"cost_price": None})


@router.post("/{product_id}/sync-marketplace", response_model=ProductOut)
def sync_marketplace_stock(
    product_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.INVENTORY_ADJUST)),
) -> ProductOut:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    try:
        from app.services.product_channels import sync_product_stock_all

        outcomes = sync_product_stock_all(db, product)
        if outcomes and "erro" in outcomes.values():
            raise RuntimeError(
                "Um ou mais canais não aceitaram o estoque; consulte o anúncio vinculado"
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao atualizar estoque no marketplace: {exc}"
        ) from exc
    db.refresh(product)
    if has_permission(actor.role, Permission.FINANCE_READ):
        return product
    return ProductOut.model_validate(product).model_copy(update={"cost_price": None})


@router.get("/{product_id}/movements", response_model=list[StockMovementOut])
def product_movements(
    product_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRODUCT_READ)),
) -> list[StockMovementOut]:
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc())
            .limit(100)
        )
    )
    if has_permission(actor.role, Permission.FINANCE_READ):
        return movements
    return [
        StockMovementOut.model_validate(movement).model_copy(
            update={"unit_cost": None, "movement_value": None}
        )
        for movement in movements
    ]
