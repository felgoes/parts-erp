from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Customer, User
from app.schemas.common import CustomerCreate, CustomerOut

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
