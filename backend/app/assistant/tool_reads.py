"""Consultas somente leitura disponíveis ao assistente."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.assistant.redaction import redact
from app.models import (
    InvoiceDocument,
    MarketplaceOrder,
    MarketplaceOrderEvent,
    Product,
    PurchaseCase,
    SalesInvoice,
)
from app.services.shipping_status import (
    DISPATCHED_SHIPPING_SUBSTATUSES,
    shipping_progress_history_exists,
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def product_view(product: Product) -> dict:
    return {
        "id": product.id,
        "sku": product.sku,
        "nome": product.name,
        "tipo": product.stock_type,
        "saldo": _decimal(product.current_stock),
        "estoque_minimo": _decimal(product.minimum_stock),
        "preco_venda": _decimal(product.sale_price),
        "preco_custo": _decimal(product.cost_price),
        "ativo": product.active,
    }


def buscar_produtos(
    db: Session, termo: str = "", limite: int = 50, abaixo_minimo: bool = False
) -> dict:
    term = (termo or "").strip()
    limit = max(1, min(int(limite or 50), 100))
    filters = [Product.active.is_(True)]
    if abaixo_minimo:
        filters.extend(
            [
                Product.stock_type == "product",
                Product.current_stock < Product.minimum_stock,
            ]
        )
    if not term:
        rows = list(db.scalars(select(Product).where(*filters).order_by(Product.name).limit(limit)))
        total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
        return {
            "ambiguo": False,
            "abaixo_minimo": abaixo_minimo,
            "total": total,
            "truncado": total > len(rows),
            "produtos": [product_view(product) for product in rows],
            "observacao": (
                f"Mostrando {len(rows)} de {total} produtos ativos; use termo para refinar."
                if total > len(rows)
                else None
            ),
        }
    exact = db.scalar(select(Product).where(Product.sku == term, *filters))
    if exact:
        return {
            "ambiguo": False,
            "abaixo_minimo": abaixo_minimo,
            "total": 1,
            "truncado": False,
            "produtos": [product_view(exact)],
        }
    term_filter = or_(
        Product.name.ilike(f"%{term}%"),
        Product.sku.ilike(f"%{term}%"),
        Product.barcode.ilike(f"%{term}%"),
    )
    filters.append(term_filter)
    rows = list(db.scalars(select(Product).where(*filters).order_by(Product.name).limit(limit)))
    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    return {
        "ambiguo": len(rows) > 1,
        "abaixo_minimo": abaixo_minimo,
        "total": total,
        "truncado": total > len(rows),
        "produtos": [product_view(product) for product in rows],
        "observacao": (
            "Há mais de um produto; peça ao administrador qual deles usar antes de agir."
            if len(rows) > 1
            else "Nenhum produto encontrado."
            if not rows
            else None
        ),
    }


def _invoice_matches(db: Session, term: str) -> list[dict]:
    matches = list(
        db.scalars(
            select(SalesInvoice)
            .where(
                or_(
                    SalesInvoice.number == term,
                    SalesInvoice.id == term,
                    SalesInvoice.marketplace_order_id == term,
                )
            )
            .limit(10)
        )
    )
    result = []
    for invoice in matches:
        order = db.scalar(select(MarketplaceOrder).where(MarketplaceOrder.invoice_id == invoice.id))
        result.append(
            {
                "tipo": "fatura",
                "id": invoice.id,
                "numero": invoice.number,
                "status": invoice.status.value,
                "origem": invoice.source.value,
                "pedido_marketplace": invoice.marketplace_order_id,
                "canal": order.provider if order else invoice.source.value,
                "emissao": _iso(invoice.issued_at),
                "total": _decimal(invoice.total),
            }
        )
    return result


def consultar_vendas(db: Session, identificador: str) -> dict:
    term = (identificador or "").strip()
    if not term:
        return {"erro": "Informe o número da venda, da fatura ou do pedido."}
    matches = _invoice_matches(db, term)
    orders = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(
                or_(
                    MarketplaceOrder.external_order_id == term,
                    MarketplaceOrder.id == term,
                )
            )
            .limit(10)
        )
    )
    for order in orders:
        if any(match["id"] == order.invoice_id for match in matches):
            continue
        matches.append(
            {
                "tipo": "pedido_marketplace",
                "id": order.id,
                "pedido": order.external_order_id,
                "canal": order.provider,
                "status": order.status,
                "fiscal": order.fiscal_status,
                "fatura_id": order.invoice_id,
                "atualizado_em": _iso(order.synchronized_at or order.updated_at),
            }
        )
    return {
        "ambiguo": len(matches) > 1,
        "resultados": matches,
        "observacao": "Peça ao administrador qual venda usar." if len(matches) > 1 else None,
    }


def listar_vendas(
    db: Session,
    status_pedido: str | None = None,
    status_envio: str | None = None,
    pendentes_envio: bool = False,
    limite: int = 10,
) -> dict:
    """Lista vendas recentes sem exigir um identificador."""
    limit = max(1, min(int(limite or 10), 50))
    query = select(MarketplaceOrder).order_by(
        MarketplaceOrder.updated_at.desc(), MarketplaceOrder.id
    )
    if status_pedido:
        query = query.where(MarketplaceOrder.status == status_pedido)
    if status_envio:
        query = query.where(MarketplaceOrder.shipping_status == status_envio)
    if pendentes_envio:
        query = query.where(
            MarketplaceOrder.shipping_status == "ready_to_ship",
            MarketplaceOrder.status.not_in(("cancelled", "canceled")),
            func.lower(func.coalesce(MarketplaceOrder.shipping_substatus, "")).not_in(
                DISPATCHED_SHIPPING_SUBSTATUSES
            ),
            ~shipping_progress_history_exists(MarketplaceOrder.id),
        )
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    orders = list(db.scalars(query.limit(limit)))
    rows = []
    for order in orders:
        invoice = db.get(SalesInvoice, order.invoice_id) if order.invoice_id else None
        rows.append(
            {
                "fatura": invoice.number if invoice else None,
                "status_fatura": invoice.status.value if invoice else None,
                "canal": order.provider,
                "pedido": order.external_order_id,
                "status_pedido": order.status,
                "status_envio": order.shipping_status,
                "substatus_envio": order.shipping_substatus,
                "etiqueta": order.label_status,
                "estado_fiscal": order.fiscal_status,
                "total": _decimal(invoice.total) if invoice else None,
                "atualizado_em": _iso(order.synchronized_at or order.updated_at),
            }
        )
    return {
        "total": total,
        "truncado": total > len(rows),
        "vendas": rows,
        "observacao": (
            f"Mostrando {len(rows)} de {total} vendas; refine o filtro se precisar."
            if total > len(rows)
            else None
        ),
    }


def _events(db: Session, order_id: str, limit: int = 20) -> list[dict]:
    rows = list(
        db.scalars(
            select(MarketplaceOrderEvent)
            .where(MarketplaceOrderEvent.order_id == order_id)
            .order_by(MarketplaceOrderEvent.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "tipo": event.event_type,
            "estado": event.status,
            "detalhe": redact(event.detail or "", 300),
            "registrado_em": _iso(event.created_at),
        }
        for event in rows
    ]


def _documents(db: Session, invoice_id: str) -> list[dict]:
    rows = list(
        db.scalars(
            select(InvoiceDocument)
            .where(InvoiceDocument.invoice_id == invoice_id)
            .order_by(InvoiceDocument.created_at)
        )
    )
    return [
        {
            "tipo": document.document_type,
            "arquivo": redact(document.filename, 120),
            "registrado_em": _iso(document.created_at),
        }
        for document in rows
    ]


def listar_compras(db: Session, busca: str | None = None, status: str | None = None) -> dict:
    query = select(PurchaseCase).order_by(PurchaseCase.created_at.desc()).limit(10)
    if busca:
        query = query.where(
            or_(
                PurchaseCase.number.ilike(f"%{busca}%"),
                PurchaseCase.supplier_name.ilike(f"%{busca}%"),
            )
        )
    if status:
        query = query.where(PurchaseCase.status == status)
    rows = list(db.scalars(query))
    return {
        "compras": [
            {
                "id": purchase.id,
                "numero": purchase.number,
                "tipo": purchase.purchase_type,
                "status": purchase.status,
                "fornecedor": purchase.supplier_name,
                "valor_despesa": _decimal(purchase.expense_amount),
                "criada_em": _iso(purchase.created_at),
            }
            for purchase in rows
        ]
    }


def investigar_fiscal(db: Session, identificador: str) -> dict:
    from app.assistant.tool_fiscal_reads import investigar_fiscal as investigate

    return investigate(db, identificador)
