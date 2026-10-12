from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_purchase_item,
    add_quote,
    cancel_purchase,
    create_purchase,
    place_order,
    remove_purchase_item,
    select_quote,
    update_purchase,
    update_purchase_item,
)
from app.api.routes.suppliers import create_supplier
from app.schemas.common import (
    PurchaseCancelRequest,
    PurchaseCreate,
    PurchaseImportDocument,
    PurchaseItemCreate,
    PurchaseItemUpdate,
    PurchaseQuoteCreate,
    PurchaseUpdate,
    SupplierCreate,
)
from tests.purchases_fixtures import (
    _actor,
)


def test_foreign_currency_requires_the_exchange_rate(db: Session) -> None:
    user = _actor()
    with pytest.raises(Exception) as error:
        create_purchase(
            PurchaseCreate(
                purchase_type="parts",
                purchase_origin="alibaba",
                supplier_order_number="ORDER-USD-1",
                original_currency="USD",
                original_total=Decimal("58.00"),
                items=[PurchaseItemCreate(description="Peça importada", quantity=1)],
            ),
            db,
            user,
        )
    assert "cotação" in str(error.value)

    purchase = create_purchase(
        PurchaseCreate(
            purchase_type="parts",
            purchase_origin="alibaba",
            supplier_order_number="ORDER-USD-1",
            original_currency="USD",
            original_total=Decimal("58.00"),
            exchange_rate=Decimal("5.350543"),
            paid_amount=Decimal("319.65"),
            items=[PurchaseItemCreate(description="Peça importada", quantity=1)],
        ),
        db,
        user,
    )
    assert purchase.original_currency == "USD"
    assert purchase.exchange_rate == Decimal("5.350543")
    assert purchase.paid_amount == Decimal("319.65")


def test_document_duplicate_is_blocked_but_cancelled_allows_proceeding(db: Session) -> None:
    user = _actor()
    payload = PurchaseCreate(
        purchase_type="parts",
        purchase_origin="aliexpress",
        supplier_order_number="ORDER-DUP-1",
        items=[PurchaseItemCreate(description="Peça repetida", quantity=1)],
    )
    first = create_purchase(payload, db, user)

    with pytest.raises(HTTPException) as error:
        create_purchase(payload, db, user)
    assert error.value.status_code == 409
    assert first.number in str(error.value.detail)

    cancel_purchase(first.id, PurchaseCancelRequest(reason="Pedido cancelado no teste"), db, user)
    again = create_purchase(payload, db, user)
    assert again.number != first.number


def test_nfe_document_identity_is_stored(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            purchase_type="parts",
            purchase_origin="nfe_xml",
            document_access_key="35260968608719000143550020000000021912749904",
            document_number="219",
            document_series="2",
            issuer_cnpj="04.617.659/0001-42",
            items=[PurchaseItemCreate(description="Peça nota", quantity=1)],
        ),
        db,
        user,
    )
    assert purchase.document_number == "219"
    assert purchase.document_series == "2"
    assert purchase.issuer_cnpj == "04.617.659/0001-42"
    assert purchase.document_access_key is not None


def test_draft_item_without_sku_is_accepted_until_the_order(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(description="Peça ainda sem código", quantity=1)]),
        db,
        user,
    )
    line = purchase.items[0]
    assert line.sku == ""

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(supplier_name="Fornecedor", total=5, item_costs={line.id: 5}),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)

    with pytest.raises(HTTPException) as error:
        place_order(purchase.id, db, user)
    assert error.value.status_code == 422
    assert "SKU" in str(error.value.detail)

    purchase = update_purchase_item(
        purchase.id,
        line.id,
        PurchaseItemUpdate(sku="SKU-OK", description="Peça identificada"),
        db,
        user,
    )
    purchase = place_order(purchase.id, db, user)
    assert purchase.status == "ordered"


def test_draft_lines_can_be_added_and_removed_with_quotes_following(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=1)]),
        db,
        user,
    )
    purchase = add_purchase_item(
        purchase.id,
        PurchaseItemCreate(sku="B", description="Peça B", quantity=2),
        db,
        user,
    )
    assert [item.sku for item in purchase.items] == ["A", "B"]
    line_b = next(item for item in purchase.items if item.sku == "B")

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor",
            total=16,
            item_costs={
                item.id: Decimal("10") if item.sku == "A" else Decimal("3")
                for item in purchase.items
            },
        ),
        db,
        user,
    )
    assert len(purchase.quotes[0].item_costs) == 2

    purchase = remove_purchase_item(purchase.id, line_b.id, db, user)

    assert [item.sku for item in purchase.items] == ["A"]
    assert line_b.id not in (purchase.quotes[0].item_costs or {})


def test_draft_header_keeps_supplier_defaults_document_fields_and_total(db: Session) -> None:
    user = _actor()
    supplier = create_supplier(
        SupplierCreate(name="Fornecedor Padrão", default_delivery_days=7), db, user
    )
    purchase = create_purchase(
        PurchaseCreate(
            supplier_id=supplier.id,
            items=[PurchaseItemCreate(sku="X", description="Peça X", quantity=2)],
        ),
        db,
        user,
    )
    assert purchase.supplier_name == "Fornecedor Padrão"
    assert purchase.needed_by is not None
    # P9: a compra nasce só com peças e quantidades — nenhum valor antes da cotação.
    assert purchase.total_amount == Decimal("0.00")
    assert purchase.items[0].unit_cost == Decimal("0.00")

    purchase = update_purchase(
        purchase.id,
        PurchaseUpdate(
            supplier_order_number="PED-99",
            document_date=datetime(2026, 10, 1, tzinfo=UTC),
            notes="Conferir na entrega",
        ),
        db,
        user,
    )

    assert purchase.supplier_order_number == "PED-99"
    assert (
        purchase.document_date is not None
        and purchase.document_date.date().isoformat() == "2026-10-01"
    )
    assert purchase.notes == "Conferir na entrega"

    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor Padrão",
            total=25,
            item_costs={line.id: Decimal("12.50")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    assert purchase.total_amount == Decimal("25.00")


def test_supplier_creation_reuses_the_existing_record(db: Session) -> None:
    user = _actor()
    first = create_supplier(SupplierCreate(name="Loja Única", contact="11 90000-0000"), db, user)
    again = create_supplier(SupplierCreate(name="Loja Única"), db, user)

    assert first.id == again.id


def test_parts_purchase_rejects_values_outside_the_quote(db: Session) -> None:
    """P9: a compra de peças nasce sem valor; quem informa custo é a cotação."""
    user = _actor()
    with pytest.raises(HTTPException) as error:
        create_purchase(
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(
                        sku="A", description="Peça A", quantity=1, unit_cost=Decimal("10")
                    )
                ]
            ),
            db,
            user,
        )
    assert error.value.status_code == 422


def test_document_import_is_the_only_parts_purchase_born_with_values(db: Session) -> None:
    """P0: o documento importado vira cotação aceita, pedido registrado e título a pagar."""
    user = _actor()
    payload = PurchaseCreate(
        source_import_id="11111111-2222-3333-4444-555555555555",
        notes="Importação de documento. Total no documento: 100.00",
        supplier_name="Fornecedor do recibo",
        document_date=datetime(2026, 10, 5, tzinfo=UTC),
        import_document=PurchaseImportDocument(filename="recibo.pdf", total=Decimal("100")),
        items=[
            PurchaseItemCreate(
                sku="DOC-1",
                description="Peça do recibo",
                quantity=2,
                unit_cost=Decimal("50"),
            )
        ],
    )
    purchase = create_purchase(payload, db, user)
    item = purchase.items[0]

    assert purchase.status == "ordered"
    assert purchase.ordered_at is not None
    assert purchase.selected_quote_id == purchase.quotes[0].id
    assert item.base_unit_cost == Decimal("50.00")
    assert item.freight_amount == Decimal("0.00")
    assert purchase.total_amount == Decimal("100.00")

    again = create_purchase(payload, db, user)
    assert again.id == purchase.id


def test_item_update_keeps_costs_pending_without_a_quote(db: Session) -> None:
    """P9: editar a peça muda descrição, SKU, unidade e quantidade — nunca o custo."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)]),
        db,
        user,
    )
    line = purchase.items[0]
    purchase = update_purchase_item(
        purchase.id,
        line.id,
        PurchaseItemUpdate(description="Peça A revisada", quantity=3, base_unit_cost=Decimal("9")),
        db,
        user,
    )
    assert purchase.items[0].quantity == Decimal("3.000")
    assert purchase.items[0].description == "Peça A revisada"
    assert purchase.items[0].base_unit_cost == Decimal("0.00")
    assert purchase.items[0].unit_cost == Decimal("0.00")
    assert purchase.total_amount == Decimal("0.00")
