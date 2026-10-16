from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.api.routes.purchases_payables import (
    _pay_purchase_now,
    _sync_payable,
)
from app.api.routes.purchases_support import (
    PAYABLE_TERM_DAYS,
    _apply_supplier_defaults,
    _event,
    _load,
    _present,
    _recompute_purchase_costs,
)
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    Product,
    PurchaseCase,
    PurchaseItem,
    PurchaseQuote,
    Supplier,
    User,
)
from app.schemas.common import (
    PurchaseCreate,
    PurchaseImportDocument,
    PurchaseOut,
)
from app.services.purchase_allocation import (
    ImportPlan,
    ImportPlanError,
    build_import_plan,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])


def _register_import_document(
    db: Session,
    purchase: PurchaseCase,
    plan: ImportPlan,
    document: PurchaseImportDocument,
    user: User,
) -> None:
    """P0: a compra importada nasce com a cotação do documento aceita e o pedido registrado.

    O documento é a prova de que a compra já foi feita: os valores revisados viram a
    proposta vencedora, o título a pagar nasce na aprovação e o pedido é registrado na
    mesma transação. Nada aqui movimenta estoque.
    """
    quote = PurchaseQuote(
        supplier_name=(purchase.supplier_name or "").strip() or "Fornecedor do documento",
        total=plan.total,
        freight_amount=plan.freight_amount,
        tax_amount=plan.tax_amount,
        extras_amount=plan.extras_amount,
        discount_amount=plan.discount_amount,
        allocation_method="proportional",
        item_costs={
            item.id: str(line.base_unit_cost)
            for item, line in zip(purchase.items, plan.lines, strict=True)
        },
        # P12, regra 7: à vista, primeiro vencimento em 30 dias corridos da data do documento.
        payment_type="cash",
        installment_count=1,
        first_due_days=PAYABLE_TERM_DAYS,
        interval_days=PAYABLE_TERM_DAYS,
        notes=f"Cotação do documento importado · {document.filename}"[:2000],
    )
    purchase.quotes.append(quote)
    db.flush()
    _event(
        db,
        purchase,
        "quote_received",
        f"Cotação do documento importado de {quote.supplier_name} registrada.",
    )
    purchase.selected_quote_id = quote.id
    purchase.status = "approved"
    _recompute_purchase_costs(purchase, quote)
    _event(db, purchase, "quote_selected", "Cotação do documento aceita na importação.")
    _sync_payable(db, purchase)
    purchase.status = "ordered"
    purchase.ordered_at = datetime.now(UTC)
    _event(
        db,
        purchase,
        "ordered",
        f"Pedido já realizado — registrado na importação do documento por {user.full_name}.",
    )


def _find_duplicate_purchase(db: Session, payload) -> PurchaseCase | None:
    """A chave de acesso identifica o documento fiscal; sem ela, número do pedido + origem."""
    access_key = (payload.document_access_key or "").strip()
    if access_key:
        match = db.scalar(
            select(PurchaseCase).where(PurchaseCase.document_access_key == access_key)
        )
        if match:
            return match
    number = (payload.supplier_order_number or "").strip()
    origin = (payload.purchase_origin or "").strip()
    if number and origin:
        return db.scalar(
            select(PurchaseCase).where(
                PurchaseCase.supplier_order_number == number,
                PurchaseCase.purchase_origin == origin,
            )
        )
    return None


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
) -> PurchaseOut:
    import_plan = None
    if payload.source_import_id:
        if not (payload.notes or "").startswith("Importação de documento."):
            raise HTTPException(status_code=422, detail="Identificador de importação inválido.")
        existing = db.scalar(
            select(PurchaseCase).where(PurchaseCase.source_import_id == payload.source_import_id)
        )
        if existing:
            return _present(_load(db, existing.id), user)
        # P0: a importação de peças nasce como compra feita (cotação do documento aceita). A
        # importação lançada como despesa (P14) segue o fluxo de despesa mais abaixo.
        if payload.purchase_type == "parts" and not payload.items:
            raise HTTPException(
                status_code=422, detail="Inclua pelo menos uma peça para importar o documento."
            )
        document = payload.import_document if payload.purchase_type == "parts" else None
        if payload.purchase_type == "parts" and document is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Importação sem os dados do documento revisado. Reenvie a revisão com o "
                    "total, frete, impostos e desconto lidos do papel."
                ),
            )
        if document is not None:
            if any(
                Decimal(item.freight_amount or 0)
                or Decimal(item.tax_amount or 0)
                or Decimal(item.discount_amount or 0)
                or Decimal(item.discount_percent or 0)
                for item in payload.items
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Os valores do documento são informados uma única vez, no fechamento da "
                        "importação, e rateados por peça."
                    ),
                )
            missing_identity = [
                item for item in payload.items if not item.sku.strip() and not item.product_id
            ]
            if missing_identity:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Informe o SKU ou vincule um produto antes de enviar o pedido: "
                        + ", ".join(item.description[:60] for item in missing_identity[:5])
                    ),
                )
            try:
                # A compra importada nasce como compra feita — cotação do documento aceita,
                # pedido registrado e título a pagar — e nada é criado se a proposta não fecha.
                import_plan = build_import_plan(
                    [
                        (
                            item.quantity,
                            item.unit_cost,
                            item.line_discount_amount,
                            item.line_total_amount,
                        )
                        for item in payload.items
                    ],
                    freight_amount=document.freight_amount,
                    tax_amount=document.tax_amount,
                    extras_amount=document.extras_amount,
                    discount_amount=document.discount_amount,
                    document_total=document.total,
                )
            except ImportPlanError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
    elif payload.purchase_type == "parts" and any(
        Decimal(item.unit_cost or 0)
        or Decimal(item.freight_amount or 0)
        or Decimal(item.tax_amount or 0)
        or Decimal(item.discount_amount or 0)
        or Decimal(item.line_discount_amount or 0)
        for item in payload.items
    ):
        # P9: a compra de peças nasce sem valor; o custo entra pela cotação ou pela
        # revisão de um documento importado (que tem fonte no papel).
        raise HTTPException(
            status_code=422,
            detail=(
                "Compras de peças são cadastradas sem valor. Informe custo, frete, impostos e "
                "desconto na cotação do fornecedor."
            ),
        )
    for item in payload.items:
        if item.product_id and not db.get(Product, item.product_id):
            raise HTTPException(status_code=404, detail=f"Produto não encontrado: {item.sku}")
        if item.product_id and payload.purchase_type == "expense":
            product = db.get(Product, item.product_id)
            if product and product.stock_type != "warehouse":
                raise HTTPException(
                    status_code=422,
                    detail="Materiais de despesas devem ser vinculados a itens do almoxarifado.",
                )
    supplier: Supplier | None = None
    if payload.supplier_id:
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    elif payload.supplier_name and payload.supplier_name.strip():
        supplier = db.scalar(select(Supplier).where(Supplier.name == payload.supplier_name.strip()))
    duplicate = _find_duplicate_purchase(db, payload)
    if duplicate and duplicate.status != "cancelled":
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Este documento já foi importado na compra {duplicate.number}."
                    " Abra a compra existente ou marque a diferença no documento."
                ),
                "purchase_id": duplicate.id,
                "purchase_number": duplicate.number,
                "purchase_status": duplicate.status,
            },
        )
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status=("ordered" if payload.items else "received")
        if payload.purchase_type == "expense"
        else "negotiating",
        purchase_type=payload.purchase_type,
        expense_category=payload.expense_category,
        expense_amount=payload.expense_amount,
        expense_description=(payload.expense_description or "").strip() or None,
        supplier_name=payload.supplier_name or (supplier.name if supplier else None),
        supplier_id=supplier.id if supplier else None,
        supplier_order_number=payload.supplier_order_number,
        purchase_origin=payload.purchase_origin,
        document_access_key=payload.document_access_key,
        document_number=payload.document_number,
        document_series=payload.document_series,
        issuer_cnpj=payload.issuer_cnpj,
        original_currency=payload.original_currency,
        original_total=payload.original_total,
        exchange_rate=payload.exchange_rate,
        paid_amount=payload.paid_amount,
        document_date=payload.document_date,
        needed_by=payload.needed_by,
        notes=payload.notes,
        source_import_id=payload.source_import_id,
        items=[
            PurchaseItem(
                **item.model_dump(exclude={"line_discount_amount", "line_total_amount"}),
                base_unit_cost=item.unit_cost,
            )
            for item in payload.items
        ],
    )
    _apply_supplier_defaults(purchase, supplier)
    db.add(purchase)
    db.flush()
    _event(db, purchase, "created", f"Compra criada por {user.full_name}.", user=user)
    if import_plan is not None and payload.import_document is not None:
        _register_import_document(db, purchase, import_plan, payload.import_document, user)
    elif payload.purchase_type == "expense":
        _sync_payable(
            db,
            purchase,
            condition=(
                payload.payment_type,
                payload.installment_count,
                payload.first_due_days,
                payload.interval_days,
            ),
        )
    if payload.paid_now:
        _pay_purchase_now(db, purchase, payload, user)
    db.commit()
    return _present(_load(db, purchase.id), user)
