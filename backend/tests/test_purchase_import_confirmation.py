from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import create_purchase
from app.models import PurchaseCase, StockMovement
from app.schemas.common import PurchaseItemCreate
from app.services.purchase_allocation import ImportPlanError, build_import_plan
from tests.import_fixtures import (
    _actor,
    _import_payload,
    _two_line_import,
)


def test_import_confirmation_creates_accepted_quote_order_and_payable(db: Session) -> None:
    """P0: uma transação cria a compra, a cotação do documento aceita, o título e o pedido."""
    user = _actor()
    purchase = create_purchase(_two_line_import(), db, user)

    assert purchase.status == "ordered"
    assert purchase.ordered_at is not None
    assert len(purchase.quotes) == 1
    quote = purchase.quotes[0]
    assert purchase.selected_quote_id == quote.id
    assert quote.total == Decimal("112.00")
    assert quote.notes == "Cotação do documento importado · recibo.pdf"
    assert (quote.payment_type, quote.installment_count, quote.first_due_days) == ("cash", 1, 30)

    item = purchase.items[0]
    assert item.base_unit_cost == Decimal("50.00")
    assert (item.freight_amount, item.tax_amount, item.discount_amount) == (
        Decimal("10.00"),
        Decimal("5.00"),
        Decimal("3.00"),
    )
    assert item.unit_cost == Decimal("56.00")

    payable = purchase.payables[0]
    assert payable.amount == Decimal("112.00")
    assert payable.due_date.replace(tzinfo=UTC) == datetime(2026, 11, 4, tzinfo=UTC)
    assert payable.installments[0].due_date.replace(tzinfo=UTC) == datetime(2026, 11, 4, tzinfo=UTC)

    required = [
        event.event_type
        for event in purchase.events
        if event.event_type in {"created", "quote_received", "quote_selected", "ordered"}
    ]
    assert required == ["created", "quote_received", "quote_selected", "ordered"]
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_import_preview_matches_persisted_values_with_cent_residue(db: Session) -> None:
    """O rateio mostrado na revisão é o mesmo que fica gravado, inclusive na sobra de centavos."""
    user = _actor()
    lines = [
        (Decimal("1"), Decimal("10.00"), Decimal("0")),
        (Decimal("1"), Decimal("10.00"), Decimal("0")),
        (Decimal("1"), Decimal("10.01"), Decimal("0")),
    ]
    plan = build_import_plan(
        lines,
        freight_amount=Decimal("10.00"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        document_total=None,
    )
    payload = _import_payload(
        total=None,
        freight=Decimal("10.00"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        items=[
            PurchaseItemCreate(
                sku=f"DOC-{index}", description=f"Peça {index}", quantity=quantity, unit_cost=cost
            )
            for index, (quantity, cost, _) in enumerate(lines, start=1)
        ],
    )
    purchase = create_purchase(payload, db, user)

    assert sum(line.freight_amount for line in plan.lines) == Decimal("10.00")
    for item, line in zip(purchase.items, plan.lines, strict=True):
        assert item.base_unit_cost == line.base_unit_cost
        assert item.unit_cost == line.unit_cost
        assert item.freight_amount == line.freight_amount
    assert purchase.quotes[0].total == plan.total == Decimal("40.01")
    assert purchase.payables[0].amount == plan.total
    # Mesmos números fixados no espelho do frontend (purchase-import-math.spec.ts).
    assert [line.freight_amount for line in plan.lines] == [
        Decimal("3.33"),
        Decimal("3.33"),
        Decimal("3.34"),
    ]
    assert [line.unit_cost for line in plan.lines] == [
        Decimal("13.33"),
        Decimal("13.33"),
        Decimal("13.35"),
    ]
    assert purchase.quotes[0].item_costs == {
        item.id: line.base_unit_cost for item, line in zip(purchase.items, plan.lines, strict=True)
    }


def test_import_blocks_when_the_total_does_not_close_and_creates_nothing(db: Session) -> None:
    user = _actor()
    payload = _two_line_import()
    payload.import_document.total = Decimal("300.00")

    with pytest.raises(HTTPException) as error:
        create_purchase(payload, db, user)

    assert error.value.status_code == 422
    assert "não fecha com o total do documento" in error.value.detail
    assert "R$ 188,00" in error.value.detail
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 0


def test_import_accepts_a_one_cent_difference_per_line(db: Session) -> None:
    """A tolerância de R$ 0,01 por item aceita a diferença de arredondamento do papel."""
    user = _actor()
    payload = _import_payload(
        total=Decimal("100.01"),
        freight=Decimal("0"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        items=[
            PurchaseItemCreate(
                sku="DOC-1", description="Filtro de óleo", quantity=1, unit_cost=Decimal("100")
            )
        ],
    )
    purchase = create_purchase(payload, db, user)

    assert purchase.quotes[0].total == Decimal("100.01")
    assert purchase.payables[0].amount == Decimal("100.01")


def test_import_blocks_when_freight_and_taxes_exceed_the_total(db: Session) -> None:
    user = _actor()
    payload = _import_payload(
        total=Decimal("10.00"),
        freight=Decimal("20.00"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        items=[
            PurchaseItemCreate(
                sku="DOC-1", description="Filtro de óleo", quantity=1, unit_cost=Decimal("10")
            )
        ],
    )
    with pytest.raises(HTTPException) as error:
        create_purchase(payload, db, user)

    assert error.value.status_code == 422
    assert "superam o total do documento" in error.value.detail
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 0


def test_import_blocks_a_line_discount_that_makes_the_cost_negative(db: Session) -> None:
    user = _actor()
    payload = _import_payload(
        total=None,
        freight=Decimal("0"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        items=[
            PurchaseItemCreate(
                sku="DOC-1",
                description="Filtro de óleo",
                quantity=1,
                unit_cost=Decimal("10"),
                line_discount_amount=Decimal("15"),
            )
        ],
    )
    with pytest.raises(HTTPException) as error:
        create_purchase(payload, db, user)

    assert error.value.status_code == 422
    assert "desconto da linha" in error.value.detail
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 0


def test_import_requires_sku_or_linked_product(db: Session) -> None:
    user = _actor()
    payload = _import_payload(
        total=None,
        freight=Decimal("0"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        items=[
            PurchaseItemCreate(description="Filtro sem código", quantity=1, unit_cost=Decimal("10"))
        ],
    )
    with pytest.raises(HTTPException) as error:
        create_purchase(payload, db, user)

    assert error.value.status_code == 422
    assert "Informe o SKU ou vincule um produto antes de enviar o pedido" in error.value.detail
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 0


def test_import_is_idempotent_and_never_moves_stock(db: Session) -> None:
    user = _actor()
    payload = _two_line_import()
    purchase = create_purchase(payload, db, user)
    again = create_purchase(payload, db, user)

    assert again.id == purchase.id
    assert db.scalar(select(func.count()).select_from(PurchaseCase)) == 1
    assert len(again.quotes) == 1
    assert len(again.payables) == 1
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_import_plan_rejects_impossible_documents_without_side_effects() -> None:
    """O rateio é puro: proposta impossível levanta erro e nada é calculado pela metade."""
    with pytest.raises(ImportPlanError):
        build_import_plan(
            [(Decimal("1"), Decimal("10.00"), Decimal("0"))],
            freight_amount=Decimal("20.00"),
            document_total=Decimal("10.00"),
        )
    with pytest.raises(ImportPlanError):
        build_import_plan([])
