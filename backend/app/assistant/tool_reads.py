"""Consultas somente leitura disponíveis ao assistente."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
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


def buscar_produtos(db: Session, termo: str, limite: int = 8) -> dict:
    term = (termo or "").strip()
    if not term:
        return {"erro": "Informe o nome, SKU ou código de barras do produto."}
    limit = max(1, min(int(limite or 8), 20))
    exact = db.scalar(select(Product).where(Product.sku == term))
    if exact:
        return {"ambiguo": False, "produtos": [product_view(exact)]}
    rows = list(
        db.scalars(
            select(Product)
            .where(
                or_(
                    Product.name.ilike(f"%{term}%"),
                    Product.sku.ilike(f"%{term}%"),
                    Product.barcode.ilike(f"%{term}%"),
                )
            )
            .order_by(Product.name)
            .limit(limit)
        )
    )
    return {
        "ambiguo": len(rows) > 1,
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
        order = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.invoice_id == invoice.id)
        )
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


def investigar_fiscal(db: Session, identificador: str) -> dict:
    """Monta evidências locais. Não faz chamada ao marketplace nem ao emissor."""
    found = consultar_vendas(db, identificador)
    matches = found.get("resultados") or []
    if not matches:
        return {
            "encontrado": False,
            "limitacao": (
                "Nenhuma venda, fatura ou pedido local corresponde ao identificador. "
                "Não há evidência suficiente para afirmar a causa; nenhuma consulta externa "
                "foi feita."
            ),
        }
    if len(matches) > 1:
        return {"encontrado": True, "ambiguo": True, "resultados": matches}
    match = matches[0]
    order: MarketplaceOrder | None = None
    invoice: SalesInvoice | None = None
    if match["tipo"] == "fatura":
        invoice = db.get(SalesInvoice, match["id"])
        order = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.invoice_id == match["id"])
        )
    else:
        order = db.get(MarketplaceOrder, match["id"])
        invoice = db.get(SalesInvoice, order.invoice_id) if order and order.invoice_id else None
    evidence: dict = {
        "encontrado": True,
        "fonte": "estados e registros locais do ERP",
        "consulta_externa": False,
        "fatura_interna": None,
        "nota_fiscal": None,
        "pedido": None,
        "eventos": [],
    }
    if invoice:
        evidence["fatura_interna"] = {
            "numero": invoice.number,
            "status": invoice.status.value,
            "origem": invoice.source.value,
            "emitida_em": _iso(invoice.issued_at),
            "total": _decimal(invoice.total),
            "documentos": _documents(db, invoice.id),
        }
    if order:
        payload = order.payload if isinstance(order.payload, dict) else {}
        evidence["pedido"] = {
            "canal": order.provider,
            "pedido": order.external_order_id,
            "status": order.status,
            "estado_fiscal": order.fiscal_status,
            "erro_fiscal": redact(order.fiscal_error or "", 800) or None,
            "nota_externa_id": order.external_invoice_id,
            "etiqueta": {
                "status": order.label_status,
                "erro": redact(order.label_error or "", 300) or None,
            },
            "sincronizado_em": _iso(order.synchronized_at),
            "ultima_atualizacao_em": _iso(order.updated_at),
            "data_origem": _iso(
                datetime.fromtimestamp(payload["last_updated"], UTC)
                if isinstance(payload.get("last_updated"), (int, float))
                else None
            ),
        }
        evidence["eventos"] = _events(db, order.id)
    evidence["nota_fiscal"] = {
        "presente": bool(order and order.external_invoice_id),
        "identificador": order.external_invoice_id if order else None,
        "observacao": (
            "Fatura interna não equivale a nota fiscal autorizada. "
            "O estado fiscal acima vem do último registro local."
        ),
    }
    if not order:
        evidence["limitacao"] = (
            "A venda não possui pedido de marketplace vinculado; só existem dados da fatura "
            "interna e não há evidência local sobre a emissão fiscal."
        )
    elif order.fiscal_status not in {"authorized", "error"}:
        evidence["limitacao"] = (
            "O estado fiscal local não é conclusivo; verifique novamente após a próxima "
            "sincronização antes de afirmar a causa."
        )
    return evidence


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
