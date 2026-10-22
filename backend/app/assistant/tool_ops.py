"""Consultas operacionais do dia a dia: resumo, financeiro, clientes e estoque."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.assistant.budget import ERP_TZ, month_window
from app.assistant.redaction import redact
from app.assistant.tool_reads import _decimal, _events, _iso, consultar_vendas
from app.models import (
    Customer,
    InvoiceDocument,
    MarketplaceOrder,
    Product,
    PurchasePayable,
    SalesInvoice,
    StockMovement,
)
from app.services.shipping_status import (
    DISPATCHED_SHIPPING_SUBSTATUSES,
    shipping_progress_history_exists,
)


def _money(value: object) -> str:
    return f"{(Decimal(str(value or 0))):.2f}"


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    return f"***{value[-4:]}" if len(value) > 4 else "***"


def _mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return _mask(value)
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"


def resumo_operacional(db: Session) -> dict:
    now = datetime.now(UTC)
    local_now = now.astimezone(ERP_TZ)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    tomorrow = (today_start + timedelta(days=1))
    month_start, month_end = month_window(now)

    def sales(start: datetime, end: datetime) -> dict:
        total = db.scalar(
            select(func.coalesce(func.sum(SalesInvoice.total), 0)).where(
                SalesInvoice.status == "confirmed",
                SalesInvoice.issued_at >= start,
                SalesInvoice.issued_at < end,
            )
        )
        count = db.scalar(
            select(func.count()).select_from(SalesInvoice).where(
                SalesInvoice.status == "confirmed",
                SalesInvoice.issued_at >= start,
                SalesInvoice.issued_at < end,
            )
        )
        return {"quantidade": count or 0, "total": _money(total)}

    pending_shipments = db.scalar(
        select(func.count()).select_from(MarketplaceOrder).where(
            MarketplaceOrder.shipping_status == "ready_to_ship",
            MarketplaceOrder.status.not_in(("cancelled", "canceled")),
            func.lower(func.coalesce(MarketplaceOrder.shipping_substatus, "")).not_in(
                DISPATCHED_SHIPPING_SUBSTATUSES
            ),
            ~shipping_progress_history_exists(MarketplaceOrder.id),
        )
    ) or 0
    fiscal_errors = db.scalar(
        select(func.count()).select_from(MarketplaceOrder).where(
            MarketplaceOrder.fiscal_status == "error"
        )
    ) or 0
    low_stock = db.scalar(
        select(func.count()).select_from(Product).where(
            Product.active.is_(True),
            Product.stock_type == "product",
            Product.current_stock < Product.minimum_stock,
        )
    ) or 0
    overdue = select(PurchasePayable).where(
        PurchasePayable.status == "open", PurchasePayable.due_date < now
    )
    overdue_count = db.scalar(
        select(func.count()).select_from(overdue.order_by(None).subquery())
    ) or 0
    overdue_total = db.scalar(
        select(
            func.coalesce(
                func.sum(PurchasePayable.amount - PurchasePayable.paid_amount), 0
            )
        ).where(PurchasePayable.status == "open", PurchasePayable.due_date < now)
    )
    return {
        "vendas_hoje": sales(today_start, tomorrow),
        "vendas_mes": sales(month_start, month_end),
        "pedidos_prontos_para_envio": pending_shipments,
        "erros_fiscais": fiscal_errors,
        "produtos_abaixo_do_minimo": low_stock,
        "contas_vencidas": {"quantidade": overdue_count, "saldo": _money(overdue_total)},
        "atualizado_em": _iso(now),
        "obs": "Valores e contagens calculados nos dados locais do ERP.",
    }


def listar_contas_a_pagar(
    db: Session, vencidas: bool = False, status: str = "open", limite: int = 10
) -> dict:
    limit = max(1, min(int(limite or 10), 50))
    now = datetime.now(UTC)
    filters = [PurchasePayable.status == status]
    if vencidas:
        filters.append(PurchasePayable.due_date < now)
    total = db.scalar(
        select(func.count())
        .select_from(PurchasePayable)
        .where(*filters)
    ) or 0
    balance = db.scalar(
        select(
            func.coalesce(func.sum(PurchasePayable.amount - PurchasePayable.paid_amount), 0)
        ).where(*filters)
    )
    rows = list(
        db.scalars(
            select(PurchasePayable)
            .where(*filters)
            .order_by(PurchasePayable.due_date)
            .limit(limit)
        )
    )
    items = []
    for payable in rows:
        due = payable.due_date
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        days = (now - due.astimezone(UTC)).days
        items.append(
            {
                "id": payable.id,
                "fornecedor": payable.supplier_name,
                "valor": _money(payable.amount),
                "pago": _money(payable.paid_amount),
                "saldo": _money(
                    Decimal(payable.amount) - Decimal(payable.paid_amount or 0)
                ),
                "vencimento": _iso(due),
                "dias_em_atraso": max(0, days),
                "status": payable.status,
                "compra": payable.purchase.number if payable.purchase else None,
            }
        )
    return {
        "total": total,
        "saldo_total": _money(balance),
        "truncado": total > len(items),
        "contas": items,
    }


def buscar_clientes(db: Session, termo: str = "", limite: int = 10) -> dict:
    limit = max(1, min(int(limite or 10), 30))
    query = select(Customer).order_by(Customer.name).limit(limit)
    term = (termo or "").strip()
    if term:
        query = query.where(
            or_(
                Customer.name.ilike(f"%{term}%"),
                Customer.document.ilike(f"%{term}%"),
                Customer.email.ilike(f"%{term}%"),
                Customer.phone.ilike(f"%{term}%"),
            )
        )
    rows = list(db.scalars(query))
    customers = []
    for customer in rows:
        count, total = db.execute(
            select(
                func.count(SalesInvoice.id),
                func.coalesce(func.sum(SalesInvoice.total), 0),
            ).where(
                SalesInvoice.customer_id == customer.id,
                SalesInvoice.status == "confirmed",
            )
        ).one()
        customers.append(
            {
                "id": customer.id,
                "nome": customer.name,
                "documento": _mask(customer.document),
                "email": _mask_email(customer.email),
                "telefone": _mask(customer.phone),
                "compras_confirmadas": count or 0,
                "total_comprado": _money(total),
            }
        )
    return {
        "clientes": customers,
        "observacao": (
            "Contato mascarado por privacidade; os dados completos ficam no cadastro do ERP."
            if customers
            else "Nenhum cliente encontrado."
        ),
    }


def movimentacoes_estoque(db: Session, sku: str | None = None, limite: int = 15) -> dict:
    limit = max(1, min(int(limite or 15), 50))
    query = (
        select(StockMovement, Product)
        .join(Product, Product.id == StockMovement.product_id)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
    )
    term = (sku or "").strip()
    if term:
        matches = list(
            db.scalars(select(Product).where(Product.sku.ilike(f"%{term}%")).limit(8))
        )
        if not matches:
            return {"erro": "Produto não encontrado.", "movimentacoes": []}
        if len(matches) > 1:
            return {
                "ambiguo": True,
                "produtos": [{"sku": item.sku, "nome": item.name} for item in matches],
                "movimentacoes": [],
                "observacao": "Peça ao administrador qual SKU usar.",
            }
        query = query.where(Product.id == matches[0].id)
    rows = db.execute(query).all()
    return {
        "movimentacoes": [
            {
                "sku": product.sku,
                "produto": product.name,
                "tipo": movement.movement_type.value,
                "quantidade": _decimal(movement.quantity),
                "saldo_apos": _decimal(movement.balance_after),
                "motivo": redact(movement.reason or "", 200),
                "referencia": redact(movement.reference or "", 100) or None,
                "registrado_em": _iso(movement.created_at),
            }
            for movement, product in rows
        ]
    }


def listar_erros_fiscais(db: Session, limite: int = 10) -> dict:
    limit = max(1, min(int(limite or 10), 30))
    rows = list(
        db.scalars(
            select(MarketplaceOrder)
            .where(MarketplaceOrder.fiscal_status == "error")
            .order_by(MarketplaceOrder.updated_at.desc())
            .limit(limit)
        )
    )
    result = []
    for order in rows:
        invoice = db.get(SalesInvoice, order.invoice_id) if order.invoice_id else None
        result.append(
            {
                "pedido": order.external_order_id,
                "canal": order.provider,
                "status_pedido": order.status,
                "fatura": invoice.number if invoice else None,
                "erro": redact(order.fiscal_error or "", 500) or None,
                "atualizado_em": _iso(order.updated_at),
            }
        )
    return {"total": len(result), "erros": result, "consulta_externa": False}


def detalhar_venda(db: Session, identificador: str) -> dict:
    found = consultar_vendas(db, identificador)
    matches = found.get("resultados") or []
    if not matches:
        return {"encontrado": False, "erro": "Venda não encontrada nos registros locais."}
    if len(matches) > 1:
        return {"encontrado": True, "ambiguo": True, "resultados": matches}
    match = matches[0]
    invoice = db.get(SalesInvoice, match["id"]) if match["tipo"] == "fatura" else None
    order = None
    if invoice:
        order = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.invoice_id == invoice.id)
        )
    else:
        order = db.get(MarketplaceOrder, match["id"])
        invoice = db.get(SalesInvoice, order.invoice_id) if order and order.invoice_id else None
    customer = db.get(Customer, invoice.customer_id) if invoice and invoice.customer_id else None
    detail: dict = {
        "encontrado": True,
        "fonte": "estados e registros locais do ERP",
        "consulta_externa": False,
        "cliente": customer.name if customer else None,
        "fatura": None,
        "itens": [],
        "documentos": [],
        "envio": None,
        "fiscal": None,
        "eventos": [],
    }
    if invoice:
        detail["fatura"] = {
            "numero": invoice.number,
            "status": invoice.status.value,
            "origem": invoice.source.value,
            "emitida_em": _iso(invoice.issued_at),
            "subtotal": _money(invoice.subtotal),
            "frete": _money(invoice.shipping),
            "desconto": _money(invoice.discount),
            "total": _money(invoice.total),
            "observacoes": redact(invoice.notes or "", 400) or None,
        }
        detail["itens"] = [
            {
                "sku": item.sku,
                "descricao": item.description,
                "quantidade": _decimal(item.quantity),
                "preco_unitario": _money(item.unit_price),
                "total": _money(item.total),
            }
            for item in invoice.items
        ]
        documents = list(
            db.scalars(
                select(InvoiceDocument).where(InvoiceDocument.invoice_id == invoice.id)
            )
        )
        detail["documentos"] = [
            {
                "tipo": document.document_type,
                "arquivo": redact(document.filename, 120),
                "registrado_em": _iso(document.created_at),
            }
            for document in documents
        ]
    if order:
        detail["envio"] = {
            "canal": order.provider,
            "pedido": order.external_order_id,
            "status_pedido": order.status,
            "status_envio": order.shipping_status,
            "substatus_envio": order.shipping_substatus,
            "etiqueta": order.label_status,
            "erro_etiqueta": redact(order.label_error or "", 300) or None,
            "sincronizado_em": _iso(order.synchronized_at),
        }
        detail["fiscal"] = {
            "status": order.fiscal_status,
            "erro": redact(order.fiscal_error or "", 500) or None,
            "nota_externa_id": order.external_invoice_id,
        }
        detail["eventos"] = _events(db, order.id, 10)
    return detail
