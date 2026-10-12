from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_support import (
    _event,
    _load,
    _present,
    _recompute_purchase_costs,
)
from app.core.config import get_settings
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    Product,
    PurchaseAttachment,
    PurchaseItem,
    User,
)
from app.schemas.common import (
    PurchaseItemCreate,
    PurchaseItemUpdate,
    PurchaseOut,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])


@router.post("/{purchase_id}/attachments", response_model=PurchaseOut)
def upload_purchase_attachments(
    purchase_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id)
    if not files or len(files) > 10:
        raise HTTPException(status_code=422, detail="Envie de 1 a 10 documentos por vez.")
    existing_size = sum(item.size_bytes for item in purchase.attachments)
    base_dir = Path(get_settings().documents_dir).resolve() / "purchases" / purchase.id
    base_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    try:
        for upload in files:
            content = upload.file.read(15 * 1024 * 1024 + 1)
            if not content or len(content) > 15 * 1024 * 1024:
                raise HTTPException(status_code=422, detail="Cada documento deve ter até 15 MB.")
            filename = Path(upload.filename or "documento").name[:255]
            path = (base_dir / f"{uuid4().hex}_{filename}").resolve()
            if base_dir not in path.parents:
                raise HTTPException(status_code=422, detail="Nome de arquivo inválido.")
            path.write_bytes(content)
            saved.append(path)
            db.add(
                PurchaseAttachment(
                    purchase_id=purchase.id,
                    filename=filename,
                    content_type=upload.content_type or "application/octet-stream",
                    size_bytes=len(content),
                    storage_path=str(path),
                )
            )
            existing_size += len(content)
        if existing_size > 100 * 1024 * 1024:
            raise HTTPException(
                status_code=422, detail="O limite total de documentos desta compra é 100 MB."
            )
        _event(
            db,
            purchase,
            "attachment_added",
            f"{len(files)} documento(s) anexado(s) por {user.full_name}.",
        )
        db.commit()
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        db.rollback()
        raise
    finally:
        for upload in files:
            upload.file.close()
    return _present(_load(db, purchase.id), user)


@router.get("/{purchase_id}/attachments/{attachment_id}")
def download_purchase_attachment(
    purchase_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> FileResponse:
    attachment = db.scalar(
        select(PurchaseAttachment).where(
            PurchaseAttachment.id == attachment_id, PurchaseAttachment.purchase_id == purchase_id
        )
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return FileResponse(
        attachment.storage_path, media_type=attachment.content_type, filename=attachment.filename
    )


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> PurchaseOut:
    return _present(_load(db, purchase_id), user)


@router.patch("/{purchase_id}/items/{item_id}", response_model=PurchaseOut)
def update_purchase_item(
    purchase_id: str,
    item_id: str,
    payload: PurchaseItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id)
    if purchase.purchase_type != "parts":
        raise HTTPException(
            status_code=409, detail="Os itens só podem ser alterados em compras de peças."
        )
    if purchase.status in {"received", "cancelled", "closed"}:
        raise HTTPException(
            status_code=409, detail="Os itens não podem mais ser alterados nesta etapa."
        )
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    changes = payload.model_dump(exclude_unset=True)
    if (
        purchase.status not in {"negotiating", "approved"}
        and {"description", "sku", "unit"} & changes.keys()
    ):
        raise HTTPException(
            status_code=409,
            detail="Descrição, SKU e unidade só podem ser alterados antes do pedido ao fornecedor.",
        )
    if payload.quantity is not None and payload.quantity < item.received_quantity:
        raise HTTPException(
            status_code=422, detail="A quantidade não pode ser menor que o já recebido."
        )
    for field, value in changes.items():
        if value is not None:
            setattr(item, field, value)
    selected = next(
        (quote for quote in purchase.quotes if quote.id == purchase.selected_quote_id), None
    )
    _recompute_purchase_costs(purchase, selected)
    _event(
        db,
        purchase,
        "item_updated",
        f"Dados de {item.description} atualizados por {user.full_name}.",
    )
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.post("/{purchase_id}/items", response_model=PurchaseOut, status_code=201)
def add_purchase_item(
    purchase_id: str,
    payload: PurchaseItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.purchase_type != "parts":
        raise HTTPException(
            status_code=409, detail="Itens só podem ser incluídos em compras de peças."
        )
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="Só é possível incluir itens durante a negociação."
        )
    if len(purchase.items) >= 100:
        raise HTTPException(status_code=422, detail="Esta compra já atingiu o limite de 100 itens.")
    if payload.product_id and not db.get(Product, payload.product_id):
        raise HTTPException(status_code=404, detail=f"Produto não encontrado: {payload.sku}")
    # Peça incluída na negociação entra sem valor: o custo só existe depois da cotação.
    item = PurchaseItem(
        product_id=payload.product_id,
        sku=payload.sku,
        description=payload.description,
        unit=payload.unit,
        quantity=payload.quantity,
        base_unit_cost=Decimal("0"),
    )
    purchase.items.append(item)
    db.flush()
    _recompute_purchase_costs(purchase)
    _event(
        db,
        purchase,
        "item_added",
        f"{item.description} incluída na negociação por {user.full_name}.",
        item=item,
        user=user,
    )
    db.commit()
    return _present(_load(db, purchase.id), user)


@router.delete("/{purchase_id}/items/{item_id}", response_model=PurchaseOut)
def remove_purchase_item(
    purchase_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    purchase = _load(db, purchase_id, for_update=True)
    if purchase.purchase_type != "parts":
        raise HTTPException(
            status_code=409, detail="Itens só podem ser removidos de compras de peças."
        )
    if purchase.status != "negotiating":
        raise HTTPException(
            status_code=409, detail="Só é possível remover itens durante a negociação."
        )
    item = next((entry for entry in purchase.items if entry.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada nesta compra.")
    if len(purchase.items) <= 1:
        raise HTTPException(
            status_code=422,
            detail="A compra precisa de pelo menos uma peça; exclua o rascunho se não for usá-la.",
        )
    if Decimal(item.received_quantity) > 0:
        raise HTTPException(status_code=409, detail="Esta peça já tem recebimento registrado.")
    for quote in purchase.quotes:
        costs = dict(quote.item_costs or {})
        if costs.pop(item.id, None) is not None:
            quote.item_costs = costs
    description = item.description
    purchase.items.remove(item)
    db.flush()
    _recompute_purchase_costs(purchase)
    _event(
        db,
        purchase,
        "item_removed",
        f"{description} removida da negociação por {user.full_name}.",
        user=user,
    )
    db.commit()
    return _present(_load(db, purchase.id), user)
