from datetime import UTC, date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    AfterSaleCase,
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    SalesInvoice,
    User,
)
from app.schemas.common import (
    AfterSaleCaseOut,
    InvoiceCreate,
    InvoiceCustomerOut,
    InvoiceOut,
    InvoiceTrackingEventOut,
    InvoiceTrackingOut,
)
from app.services.after_sale import after_sales_for_invoices, invoice_after_sale
from app.services.sales import cancel_invoice, confirm_invoice, create_invoice

router = APIRouter(prefix="/invoices", tags=["Faturas de venda"])
BRAZIL_TZ = timezone(timedelta(hours=-3))


def _sync_marketplace_stock_for_invoice(db: Session, invoice: SalesInvoice) -> None:
    from app.services.product_channels import sync_product_stock_all

    product_ids = {item.product_id for item in invoice.items}
    for product_id in product_ids:
        product = db.get(Product, product_id)
        if product:
            try:
                sync_product_stock_all(db, product)
            except Exception:
                # A venda local não falha se o marketplace estiver temporariamente indisponível.
                db.rollback()


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[InvoiceOut]:
    today = datetime.now(BRAZIL_TZ).date()
    start = start_date or today.replace(day=1)
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if (end - start).days > 364:
        raise HTTPException(status_code=422, detail="O período máximo é de 365 dias")
    since = datetime.combine(start, time.min, BRAZIL_TZ).astimezone(UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, BRAZIL_TZ).astimezone(UTC)
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    query = (
        select(SalesInvoice)
        .options(
            selectinload(SalesInvoice.items),
            selectinload(SalesInvoice.documents),
            selectinload(SalesInvoice.customer),
        )
        .where(invoice_date >= since, invoice_date < until)
        .order_by(SalesInvoice.created_at.desc())
        .limit(200)
    )
    invoices = list(db.scalars(query))
    after_sales = after_sales_for_invoices(db, invoices)
    outputs = []
    for invoice in invoices:
        output = InvoiceOut.model_validate(invoice)
        output.after_sale = after_sales.get(invoice.id)
        outputs.append(output)
    return outputs


@router.post("", response_model=InvoiceOut, status_code=201)
def add_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_CREATE)),
) -> SalesInvoice:
    invoice = create_invoice(db, payload)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_READ)),
) -> InvoiceOut:
    invoice = db.scalar(
        select(SalesInvoice)
        .options(
            selectinload(SalesInvoice.items),
            selectinload(SalesInvoice.documents),
            selectinload(SalesInvoice.customer),
        )
        .where(SalesInvoice.id == invoice_id)
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    result = InvoiceOut.model_validate(invoice)
    if invoice.customer:
        result.customer = InvoiceCustomerOut(
            name=invoice.customer.name,
            document=invoice.customer.document,
            email=invoice.customer.email,
            phone=invoice.customer.phone,
        )
    if invoice.marketplace_order_id:
        order = db.scalar(
            select(MarketplaceOrder).where(
                MarketplaceOrder.provider == "mercadolivre",
                MarketplaceOrder.external_order_id == invoice.marketplace_order_id,
            )
        )
        if order:
            result.after_sale = invoice_after_sale(order, invoice.total)
            if result.after_sale:
                return_cases = list(
                    db.scalars(
                        select(AfterSaleCase)
                        .options(
                            selectinload(AfterSaleCase.items),
                            selectinload(AfterSaleCase.events),
                        )
                        .where(AfterSaleCase.invoice_id == invoice.id)
                        .order_by(AfterSaleCase.created_at.desc())
                    )
                )
                result.after_sale.cases = [
                    AfterSaleCaseOut.model_validate(case) for case in return_cases
                ]
                result.after_sale.history = [
                    InvoiceTrackingEventOut(
                        status=event.status,
                        detail=event.detail,
                        created_at=event.created_at,
                    )
                    for event in db.scalars(
                        select(MarketplaceOrderEvent)
                        .where(
                            MarketplaceOrderEvent.order_id == order.id,
                            MarketplaceOrderEvent.event_type == "after_sale",
                        )
                        .order_by(MarketplaceOrderEvent.created_at.asc())
                    )
                ] or result.after_sale.history
            if order.shipment_id:
                account = db.scalar(
                    select(MarketplaceAccount).where(
                        MarketplaceAccount.provider == "mercadolivre",
                        MarketplaceAccount.seller_id == order.seller_id,
                        MarketplaceAccount.active.is_(True),
                    )
                )
                if account:
                    try:
                        from app.integrations.mercadolivre.sync import sync_shipping_history

                        sync_shipping_history(db, order, account)
                    except Exception:
                        # A detail screen must remain available if ML is temporarily offline.
                        db.rollback()
            events = db.scalars(
                select(MarketplaceOrderEvent)
                .where(MarketplaceOrderEvent.order_id == order.id)
                .where(MarketplaceOrderEvent.event_type == "shipment_status")
                .order_by(MarketplaceOrderEvent.created_at.asc())
            )
            result.tracking = InvoiceTrackingOut(
                shipment_id=order.shipment_id,
                status=order.status,
                shipping_status=order.shipping_status,
                label_status=order.label_status,
                last_update=order.synchronized_at or order.updated_at,
                history=[
                    InvoiceTrackingEventOut(
                        status=event.status,
                        detail=event.detail,
                        created_at=event.created_at,
                    )
                    for event in events
                ],
            )
    return result


@router.post("/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_CONFIRM)),
) -> SalesInvoice:
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    confirm_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    _sync_marketplace_stock_for_invoice(db, invoice)
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel(
    invoice_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_CANCEL)),
) -> SalesInvoice:
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    cancel_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    _sync_marketplace_stock_for_invoice(db, invoice)
    return invoice


@router.get("/{invoice_id}/documents/{document_id}")
def download_document(
    invoice_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.INVOICE_READ)),
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
