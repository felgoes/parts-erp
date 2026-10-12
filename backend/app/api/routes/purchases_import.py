from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_creation import (
    create_purchase,
)
from app.api.routes.purchases_support import (
    _event,
    _load,
    _present,
)
from app.core.config import get_settings
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    PurchaseAttachment,
    PurchaseCase,
    User,
)
from app.schemas.common import (
    PurchaseCreate,
    PurchaseOut,
)
from app.services.purchase_import import analyze_upload

router = APIRouter(prefix="/purchases", tags=["Compras"])


@router.post("/import-document/confirm", response_model=PurchaseOut, status_code=201)
async def confirm_imported_purchase(
    file: UploadFile = File(...),
    payload: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    """Cria a compra importada e anexa o documento original na mesma operação."""
    try:
        data = PurchaseCreate.model_validate_json(payload)
    except ValidationError as error:
        message = " · ".join(
            str(entry.get("msg", "")).strip() for entry in error.errors() if entry.get("msg")
        )[:400]
        raise HTTPException(
            status_code=422, detail=message or "Confira os dados da compra importada."
        ) from error
    purchase = create_purchase(data, db, user)
    stored: Path | None = None
    try:
        content = file.file.read(15 * 1024 * 1024 + 1)
        if not content or len(content) > 15 * 1024 * 1024:
            raise ValueError("O documento deve ter conteúdo e até 15 MB.")
        filename = Path(file.filename or "documento").name[:255]
        base_dir = Path(get_settings().documents_dir).resolve() / "purchases" / purchase.id
        base_dir.mkdir(parents=True, exist_ok=True)
        stored = (base_dir / f"{uuid4().hex}_{filename}").resolve()
        stored.write_bytes(content)
        db.add(
            PurchaseAttachment(
                purchase_id=purchase.id,
                filename=filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=len(content),
                storage_path=str(stored),
            )
        )
        _event(
            db,
            _load(db, purchase.id),
            "attachment_added",
            f"Documento original anexado por {user.full_name}.",
            user=user,
        )
        db.commit()
    except Exception:
        db.rollback()
        if stored is not None:
            stored.unlink(missing_ok=True)
        orphan = db.get(PurchaseCase, purchase.id)
        if orphan is not None:
            db.delete(orphan)
            db.commit()
        raise HTTPException(
            status_code=422,
            detail="Não foi possível anexar o documento original; a compra não foi criada.",
        ) from None
    finally:
        file.file.close()
    return _present(_load(db, purchase.id), user)


@router.get("/import-document/duplicates")
def import_document_duplicates(
    document_access_key: str | None = Query(default=None, max_length=44),
    order_number: str | None = Query(default=None, max_length=80),
    origin: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> dict[str, object]:
    """Antes de criar a compra, a revisão confere se o documento já entrou no ERP."""
    match: PurchaseCase | None = None
    if document_access_key and document_access_key.strip():
        match = db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.document_access_key == document_access_key.strip()
            )
        )
    if match is None and order_number and order_number.strip() and origin and origin.strip():
        match = db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.supplier_order_number == order_number.strip(),
                PurchaseCase.purchase_origin == origin.strip(),
            )
        )
    if match is None:
        return {"match": None}
    return {
        "match": {
            "purchase_id": match.id,
            "purchase_number": match.number,
            "purchase_status": match.status,
            "cancelled": match.status == "cancelled",
        }
    }


@router.post("/import-document")
async def import_purchase_document(
    file: UploadFile = File(...),
    profile_id: str | None = None,
    _: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> dict[str, object]:
    try:
        return await analyze_upload(file, profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid returning or logging document contents or OCR output.
        raise HTTPException(
            status_code=422,
            detail=(
                "Não foi possível interpretar o documento. Confira o arquivo e use a compra manual."
            ),
        ) from exc
