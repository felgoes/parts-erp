from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import AfterSaleCase, User, UserRole
from app.schemas.common import (
    AfterSaleCaseOut,
    AfterSaleCloseIn,
    AfterSaleInspectIn,
    AfterSaleReceiveIn,
)
from app.services.after_sale import (
    close_after_sale_without_stock,
    inspect_after_sale_items,
    receive_after_sale_items,
)

router = APIRouter(prefix="/after-sales", tags=["Pós-venda e devoluções"])


def _case(db: Session, case_id: str) -> AfterSaleCase:
    case = db.scalar(
        select(AfterSaleCase)
        .options(selectinload(AfterSaleCase.items), selectinload(AfterSaleCase.events))
        .where(AfterSaleCase.id == case_id)
    )
    if not case:
        raise HTTPException(status_code=404, detail="Pós-venda não encontrado")
    return case


@router.get("/{case_id}", response_model=AfterSaleCaseOut)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AfterSaleCase:
    return _case(db, case_id)


@router.post("/{case_id}/receive", response_model=AfterSaleCaseOut)
def receive_items(
    case_id: str,
    payload: AfterSaleReceiveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> AfterSaleCase:
    case = _case(db, case_id)
    try:
        result = receive_after_sale_items(db, case, payload, user)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(result)
    return result


@router.post("/{case_id}/inspect", response_model=AfterSaleCaseOut)
def inspect_items(
    case_id: str,
    payload: AfterSaleInspectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> AfterSaleCase:
    case = _case(db, case_id)
    try:
        result = inspect_after_sale_items(db, case, payload, user)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(result)
    return result


@router.post("/{case_id}/close-without-stock", response_model=AfterSaleCaseOut)
def close_without_stock(
    case_id: str,
    payload: AfterSaleCloseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> AfterSaleCase:
    case = _case(db, case_id)
    try:
        result = close_after_sale_without_stock(db, case, payload.note, user)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(result)
    return result
