"""Contrato da lista de compras (P1): linhas leves, paginação e resumo por etapa."""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import (
    PayableOut,
    PurchaseAttachmentOut,
    PurchaseEventOut,
    PurchaseOut,
)


class PurchaseListRowItem(BaseModel):
    """Item como a lista precisa dele: sem custo, frete, impostos nem desconto.

    A tela de detalhe busca o registro completo ao abrir; aqui vão só os campos que a linha
    mostra e que a seleção em lote e a cópia usam.
    """

    id: str
    product_id: str | None = None
    sku: str
    description: str
    unit: str = "un"
    quantity: Decimal
    received_quantity: Decimal


class PurchaseListRowQuote(BaseModel):
    """Cotação como a lista precisa dela: fornecedor e total, sem rateio nem condição."""

    id: str
    supplier_name: str
    total: Decimal | None = None


class PurchaseListItem(PurchaseOut):
    """Projeção da lista: sem histórico, anexos e títulos, e com itens e cotações leves."""

    events: list[PurchaseEventOut] = Field(default_factory=list, exclude=True)
    attachments: list[PurchaseAttachmentOut] = Field(default_factory=list, exclude=True)
    payables: list[PayableOut] = Field(default_factory=list, exclude=True)
    items: list[PurchaseListRowItem] = Field(default_factory=list)
    quotes: list[PurchaseListRowQuote] = Field(default_factory=list)


class PurchaseListSummary(BaseModel):
    """Contagens dos cartões, sempre do período escolhido (como a tela já mostrava)."""

    negotiating: int = 0
    ordered: int = 0
    received: int = 0


class PurchaseListOut(BaseModel):
    """Envelope da lista: a página, o total filtrado e o resumo do período."""

    items: list[PurchaseListItem] = Field(default_factory=list)
    total: int = 0
    summary: PurchaseListSummary = Field(default_factory=PurchaseListSummary)
    limit: int = 25
    offset: int = 0
