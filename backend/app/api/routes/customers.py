from fastapi import APIRouter, Depends
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Customer, MarketplaceOrder, SalesInvoice, User
from app.schemas.common import CustomerCreate, CustomerDetailOut, CustomerOut, CustomerPurchaseOut

router = APIRouter(prefix="/customers", tags=["Clientes"])


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[Customer]:
    return list(db.scalars(select(Customer).order_by(Customer.name).limit(500)))


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Customer:
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerDetailOut)
def customer_detail(
    customer_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    customer = db.get(Customer, customer_id)
    if not customer:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    invoices = list(
        db.scalars(
            select(SalesInvoice)
            .where(SalesInvoice.customer_id == customer_id)
            .order_by(SalesInvoice.created_at.desc())
        )
    )
    order_ids = {invoice.marketplace_order_id for invoice in invoices if invoice.marketplace_order_id}
    cancelled = 0
    if order_ids:
        cancelled = db.scalar(
            select(func.count(MarketplaceOrder.id)).where(
                MarketplaceOrder.external_order_id.in_(order_ids),
                MarketplaceOrder.status == "cancelled",
            )
        ) or 0
    total = sum((Decimal(invoice.total or 0) for invoice in invoices), Decimal("0"))
    confirmed = [invoice for invoice in invoices if str(invoice.status) in {"confirmed", "InvoiceStatus.confirmed"}]
    purchases = [
        CustomerPurchaseOut(
            id=invoice.id,
            number=invoice.number,
            status=str(invoice.status.value if hasattr(invoice.status, "value") else invoice.status),
            source=str(invoice.source.value if hasattr(invoice.source, "value") else invoice.source),
            marketplace_order_id=invoice.marketplace_order_id,
            total=invoice.total,
            issued_at=invoice.issued_at,
            created_at=invoice.created_at,
            item_count=len(invoice.items),
        )
        for invoice in invoices
    ]
    return {
        "id": customer.id,
        "name": customer.name,
        "document": customer.document,
        "email": customer.email,
        "phone": customer.phone,
        "created_at": customer.created_at,
        "purchase_count": len(invoices),
        "confirmed_purchase_count": len(confirmed),
        "total_purchased": total,
        "average_purchase": total / len(invoices) if invoices else Decimal("0"),
        "last_purchase_at": invoices[0].issued_at or invoices[0].created_at if invoices else None,
        "marketplace_order_count": len(order_ids),
        "cancelled_order_count": int(cancelled),
        "purchases": purchases,
    }
