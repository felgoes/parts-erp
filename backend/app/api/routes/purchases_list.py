"""Lista de compras (P1): página, busca, período, etapa e resumo.

Módulo próprio porque a lista tem um contrato diferente do detalhe — linhas leves, filtro no
servidor e paginação — e porque o arquivo de compras já está grande demais para crescer.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.api.routes.purchases import _mask_costs, _purchase_total
from app.core.periods import optional_period_window
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import PurchaseCase, PurchaseItem, User
from app.schemas.purchases_list import (
    PurchaseListItem,
    PurchaseListOut,
    PurchaseListRowItem,
    PurchaseListRowQuote,
    PurchaseListSummary,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])

LIST_STATUSES = {
    "negotiating",
    "approved",
    "ordered",
    "partially_received",
    "received",
    "closed",
    "cancelled",
}
STATUS_GROUPS = {
    "preparation": ("negotiating", "approved"),
    "receiving": ("ordered", "partially_received"),
    "finished": ("received", "closed"),
    "cancelled": ("cancelled",),
}
PurchaseStatusGroup = Literal["preparation", "receiving", "finished", "cancelled"]


@router.get("", response_model=PurchaseListOut)
def list_purchases(
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status: Annotated[str | None, Query(max_length=30)] = None,
    status_group: PurchaseStatusGroup | None = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_READ)),
) -> PurchaseListOut:
    if status is not None and status_group is not None:
        raise HTTPException(422, "Informe status ou status_group, sem combinar os dois.")
    since, until = optional_period_window(start_date, end_date)
    period_filters = []
    if since is not None:
        period_filters.append(PurchaseCase.created_at >= since)
    if until is not None:
        period_filters.append(PurchaseCase.created_at < until)

    base_filters = list(period_filters)
    term = (search or "").strip()
    if term:
        like = f"%{term}%"
        base_filters.append(
            or_(
                PurchaseCase.number.ilike(like),
                PurchaseCase.supplier_name.ilike(like),
                PurchaseCase.items.any(
                    or_(PurchaseItem.sku.ilike(like), PurchaseItem.description.ilike(like))
                ),
            )
        )

    filters = list(base_filters)
    if status_group:
        filters.append(PurchaseCase.status.in_(STATUS_GROUPS[status_group]))
    elif status in LIST_STATUSES:
        filters.append(PurchaseCase.status == status)

    total = db.scalar(select(func.count(PurchaseCase.id)).where(*filters)) or 0
    purchases = list(
        db.scalars(
            select(PurchaseCase)
            .options(selectinload(PurchaseCase.items), selectinload(PurchaseCase.quotes))
            .where(*filters)
            .order_by(PurchaseCase.created_at.desc(), PurchaseCase.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    # O resumo segue o período, não a busca nem a etapa: é o mesmo comportamento dos cartões
    # antes da paginação, quando eles contavam o período inteiro carregado na tela.
    counts = dict(
        db.execute(
            select(PurchaseCase.status, func.count(PurchaseCase.id))
            .where(*period_filters)
            .group_by(PurchaseCase.status)
        ).all()
    )
    matching_counts = counts if not term else dict(
        db.execute(
            select(PurchaseCase.status, func.count(PurchaseCase.id))
            .where(*base_filters)
            .group_by(PurchaseCase.status)
        ).all()
    )
    summary = PurchaseListSummary(
        negotiating=counts.get("negotiating", 0),
        ordered=sum(counts.get(state, 0) for state in STATUS_GROUPS["receiving"]),
        received=counts.get("received", 0),
        groups={
            group: sum(matching_counts.get(state, 0) for state in states)
            for group, states in STATUS_GROUPS.items()
        },
    )
    return PurchaseListOut(
        items=[_present_list_item(purchase, user) for purchase in purchases],
        total=total,
        summary=summary,
        limit=limit,
        offset=offset,
    )


def _present_list_item(purchase: PurchaseCase, user: User) -> PurchaseListItem:
    """Item da lista sem carregar histórico, anexos e títulos — a consulta nem os seleciona."""
    result = PurchaseListItem(
        id=purchase.id,
        number=purchase.number,
        status=purchase.status,
        purchase_type=purchase.purchase_type,
        expense_category=purchase.expense_category,
        expense_amount=purchase.expense_amount,
        expense_description=purchase.expense_description,
        supplier_name=purchase.supplier_name,
        supplier_id=purchase.supplier_id,
        supplier_order_number=purchase.supplier_order_number,
        purchase_origin=purchase.purchase_origin,
        document_access_key=purchase.document_access_key,
        document_number=purchase.document_number,
        document_series=purchase.document_series,
        issuer_cnpj=purchase.issuer_cnpj,
        original_currency=purchase.original_currency,
        original_total=purchase.original_total,
        exchange_rate=purchase.exchange_rate,
        paid_amount=purchase.paid_amount,
        document_date=purchase.document_date,
        selected_quote_id=purchase.selected_quote_id,
        needed_by=purchase.needed_by,
        ordered_at=purchase.ordered_at,
        cancel_reason=purchase.cancel_reason,
        cancelled_at=purchase.cancelled_at,
        closed_at=purchase.closed_at,
        notes=purchase.notes,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        items=[
            PurchaseListRowItem(
                id=item.id,
                product_id=item.product_id,
                sku=item.sku,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                received_quantity=item.received_quantity,
            )
            for item in purchase.items
        ],
        quotes=[
            PurchaseListRowQuote(id=quote.id, supplier_name=quote.supplier_name, total=quote.total)
            for quote in purchase.quotes
        ],
        total_amount=_purchase_total(purchase),
    )
    return _mask_costs(result, user)
