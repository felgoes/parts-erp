"""Investigação fiscal baseada somente nos registros locais do ERP."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.redaction import redact
from app.assistant.tool_reads import _decimal, _documents, _events, _iso, consultar_vendas
from app.models import MarketplaceOrder, SalesInvoice


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
