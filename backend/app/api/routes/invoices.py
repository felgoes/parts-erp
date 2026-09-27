from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import InvoiceDocument, SalesInvoice, User, UserRole
from app.schemas.common import InvoiceCreate, InvoiceOut
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice

router = APIRouter(prefix="/invoices", tags=["Faturas de venda"])


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[SalesInvoice]:
    query = select(SalesInvoice).order_by(SalesInvoice.created_at.desc()).limit(200)
    return list(db.scalars(query))


@router.post("", response_model=InvoiceOut, status_code=201)
def add_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SalesInvoice:
    invoice = create_invoice(db, payload)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SalesInvoice:
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    confirm_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> SalesInvoice:
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    cancel_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}/documents/{document_id}")
def download_document(
    invoice_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FileResponse:
    document = db.scalar(
        select(InvoiceDocument).where(
            InvoiceDocument.id == document_id, InvoiceDocument.invoice_id == invoice_id
        )
    )
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    media_type = "application/pdf" if document.document_type == "pdf" else "application/xml"
    return FileResponse(document.storage_path, media_type=media_type, filename=document.filename)
