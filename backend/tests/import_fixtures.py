from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.common import PurchaseCreate, PurchaseImportDocument, PurchaseItemCreate


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id="user-qa", full_name="QA")


def _import_payload(
    *,
    items: list[PurchaseItemCreate],
    total: Decimal | None = Decimal("112.00"),
    freight: Decimal = Decimal("10.00"),
    tax: Decimal = Decimal("5.00"),
    discount: Decimal = Decimal("3.00"),
    import_id: str = "99999999-2222-3333-4444-555555555555",
) -> PurchaseCreate:
    return PurchaseCreate(
        purchase_type="parts",
        source_import_id=import_id,
        supplier_name="Fornecedor do recibo",
        document_date=datetime(2026, 10, 5, tzinfo=UTC),
        notes="Importação de documento. Documento revisado pelo usuário.",
        import_document=PurchaseImportDocument(
            filename="recibo.pdf",
            total=total,
            freight_amount=freight,
            tax_amount=tax,
            discount_amount=discount,
        ),
        items=items,
    )


def _two_line_import() -> PurchaseCreate:
    return _import_payload(
        items=[
            PurchaseItemCreate(
                sku="DOC-1", description="Filtro de óleo", quantity=2, unit_cost=Decimal("50")
            )
        ]
    )
