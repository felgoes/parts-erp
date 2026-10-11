from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import (
    add_quote,
    add_purchase_item,
    cancel_purchase,
    close_purchase_balance,
    create_purchase,
    delete_purchase,
    get_purchase,
    place_order,
    receive_purchase_in_full,
    receive_purchase,
    remove_purchase_item,
    select_quote,
    settle_payable,
    update_purchase,
    update_purchase_item,
)
from app.api.routes.suppliers import create_supplier
from app.services.stock import move_stock
from app.models import MarketStudy, MovementType, Product, PurchaseCase, PurchaseDeletion, StockMovement
from app.schemas.common import (
    PayableUpdate,
    PurchaseCancelRequest,
    PurchaseCloseRequest,
    PurchaseCreate,
    PurchaseItemCreate,
    PurchaseOut,
    PurchaseQuoteCreate,
    PurchaseReceive,
    PurchaseReceiveItem,
    PurchaseItemUpdate,
    PurchaseUpdate,
    SupplierCreate,
)


def _actor() -> SimpleNamespace:
    """Route functions take the authenticated user; tests only need id and name."""
    return SimpleNamespace(id="user-qa", full_name="QA")


def _ordered_purchase(db: Session, user: SimpleNamespace) -> PurchaseOut:
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor A",
            supplier_order_number="PED-123",
            items=[
                PurchaseItemCreate(
                    sku="LR174890",
                    description="Kit membrana Tiggo",
                    quantity=5,
                )
            ],
        ),
        db,
        user,
    )
    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A",
            total=130,
            delivery_days=12,
            item_costs={line.id: Decimal("26")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    return place_order(purchase.id, db, user)


def test_negotiation_receiving_links_product_and_updates_stock_once(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            notes="Confirmar compatibilidade antes de fechar",
            items=[
                PurchaseItemCreate(
                    sku="LR174890",
                    description="Kit membrana Tiggo",
                    quantity=5,
                )
            ],
        ),
        db,
        user,
    )
    assert purchase.status == "negotiating"
    assert len(purchase.items) == 1
    line = purchase.items[0]

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A",
            total=150,
            delivery_days=12,
            item_costs={line.id: Decimal("30")},
        ),
        db,
        user,
    )
    quote_a = purchase.quotes[0]
    assert PurchaseOut.model_validate(purchase).quotes[0].item_costs[line.id] == Decimal("30")
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor B",
            total=130,
            delivery_days=20,
            item_costs={line.id: Decimal("26")},
        ),
        db,
        user,
    )
    quote_b = next(quote for quote in purchase.quotes if quote.supplier_name == "Fornecedor B")
    purchase = select_quote(purchase.id, quote_b.id, db, user)
    assert purchase.status == "approved"
    assert purchase.selected_quote_id == quote_b.id
    assert purchase.items[0].unit_cost == Decimal("26.00")
    assert quote_a.id != quote_b.id

    purchase = place_order(purchase.id, db, user)
    assert purchase.status == "ordered"

    first_receipt = PurchaseReceive(
        items=[
            PurchaseReceiveItem(
                item_id=line.id,
                receipt_id="receipt-test-batch-0001",
                quantity=3,
                create_product=True,
            )
        ]
    )
    purchase = receive_purchase(purchase.id, first_receipt, db, user)
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None
    assert product.current_stock == Decimal("3.000")
    assert purchase.status == "partially_received"

    # A retried request uses the same receipt id and must not post stock twice.
    purchase = receive_purchase(purchase.id, first_receipt, db, user)
    assert product.current_stock == Decimal("3.000")
    assert purchase.items[0].received_quantity == Decimal("3.000")

    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-batch-0002",
                    quantity=2,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert purchase.status == "received"
    assert product.current_stock == Decimal("5.000")
    assert db.scalar(select(func.count(StockMovement.id))) == 2
    assert all(
        movement.movement_type == MovementType.purchase_received
        for movement in db.scalars(select(StockMovement))
    )


def test_cancelled_purchase_cannot_be_received(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="P-2", description="Peça teste", quantity=1)]),
        db,
        user,
    )
    purchase = cancel_purchase(
        purchase.id, PurchaseCancelRequest(reason="Compra de teste cancelada"), db, user
    )
    assert purchase.status == "cancelled"
    assert purchase.cancel_reason == "Compra de teste cancelada"
    with pytest.raises(HTTPException) as error:
        receive_purchase(
            purchase.id,
            PurchaseReceive(
                items=[
                    PurchaseReceiveItem(
                        item_id=purchase.items[0].id,
                        receipt_id="receipt-test-cancel-0001",
                        quantity=1,
                        create_product=True,
                    )
                ]
            ),
            db,
            user,
        )
    assert error.value.status_code == 409
    assert db.scalar(select(func.count(StockMovement.id))) == 0


def test_marketplace_purchase_can_be_created_already_paid(db: Session) -> None:
    """P14: compra paga no checkout nasce com o título baixado, com data e forma."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            notes="Importação de documento. Documento revisado pelo usuário.",
            source_import_id="0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
            purchase_origin="aliexpress",
            supplier_order_number="ORDER-PAID-1",
            original_currency="BRL",
            original_total=Decimal("205.03"),
            paid_amount=Decimal("205.03"),
            paid_now=True,
            paid_date=datetime(2026, 9, 28, tzinfo=UTC),
            paid_method="Visa",
            items=[
                PurchaseItemCreate(
                    description="Peça paga no checkout", quantity=1, unit_cost=Decimal("205.03")
                )
            ],
        ),
        db,
        user,
    )

    assert len(purchase.payables) == 1
    payable = purchase.payables[0]
    assert payable.status == "paid"
    assert payable.paid_amount == Decimal("205.03")
    assert payable.amount == Decimal("205.03")


def test_draft_purchase_is_deleted_with_immutable_audit_record(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name="Fornecedor Rascunho",
            items=[
                PurchaseItemCreate(
                    sku="P-9", description="Peça em rascunho", quantity=2
                )
            ],
        ),
        db,
        user,
    )
    number = purchase.number
    record = delete_purchase(purchase.id, "Criada por engano", db, user)

    assert record.number == number
    assert record.supplier_name == "Fornecedor Rascunho"
    assert "P-9" in record.items_summary
    assert db.scalar(select(func.count(PurchaseCase.id))) == 0
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 1


def test_purchase_with_effects_is_deleted_with_its_children(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)

    record = delete_purchase(purchase.id, "Pedido criado por engano", db, user)

    assert "cotação" in record.children_summary
    assert db.get(PurchaseCase, purchase.id) is None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 1
    # Reenviar não exclui duas vezes: a compra já não existe.
    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, None, db, user)
    assert error.value.status_code == 404


def test_deleting_a_received_purchase_reverses_stock_and_keeps_the_trail(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-delete-0001",
                    quantity=3,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("3.000")

    record = delete_purchase(purchase.id, "Compra de teste", db, user)

    assert "estorno" in record.children_summary
    assert "título a pagar" in record.children_summary
    assert db.get(PurchaseCase, purchase.id) is None
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("0.000")
    movements = list(db.scalars(select(StockMovement).order_by(StockMovement.created_at)))
    assert [movement.movement_type for movement in movements] == [
        MovementType.purchase_received,
        MovementType.cancellation,
    ]


def test_deletion_is_blocked_when_the_reversal_would_leave_negative_stock(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-delete-0002",
                    quantity=4,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    product_id = db.scalar(select(Product.id).where(Product.sku == "LR174890"))
    move_stock(
        db,
        product_id=product_id,
        quantity=Decimal("-3"),
        movement_type=MovementType.sale,
        reason="Venda de teste",
        reference="QA",
        idempotency_key="qa-sale-delete-guard",
        unit_cost=Decimal("26.00"),
    )
    db.commit()

    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, "Tentativa", db, user)

    assert error.value.status_code == 409
    assert "Estoque insuficiente" in str(error.value.detail)
    assert db.get(PurchaseCase, purchase.id) is not None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 0


def test_deletion_is_blocked_by_registered_payment(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    purchase = receive_purchase_in_full(purchase.id, None, True, db, user)
    payable = purchase.payables[0]
    settle_payable(purchase.id, payable.id, PayableUpdate(payment_method="Pix"), db, user)

    with pytest.raises(HTTPException) as error:
        delete_purchase(purchase.id, "Com pagamento", db, user)

    assert error.value.status_code == 409
    assert "pagamento" in str(error.value.detail)
    assert db.get(PurchaseCase, purchase.id) is not None
    assert db.scalar(select(func.count(PurchaseDeletion.id))) == 0


def test_market_study_keeps_existing_and_only_loses_the_link(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[PurchaseItemCreate(sku="P-77", description="Peça estudo", quantity=1)]
        ),
        db,
        user,
    )
    study = MarketStudy(
        id="study-qa-1",
        created_by_id="user-qa",
        search_term="Peça estudo",
        landed_cost=Decimal("10.00"),
        target_margin_pct=Decimal("20.00"),
        marketplace_fee_pct=Decimal("10.00"),
        linked_purchase_id=purchase.id,
    )
    db.add(study)
    db.commit()

    delete_purchase(purchase.id, "Compra ligada a estudo", db, user)

    stored = db.get(MarketStudy, "study-qa-1")
    assert stored is not None
    assert stored.linked_purchase_id is None


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


def test_receive_all_marks_every_item_received(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)

    purchase = receive_purchase_in_full(purchase.id, None, True, db, user)

    assert purchase.status == "received"
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None and product.current_stock == Decimal("5.000")
    assert purchase.payables[0].amount == Decimal("130.00")


def test_partial_receipt_cancel_returns_stock_and_closes_the_payable(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-return-0001",
                    quantity=3,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    product = db.scalar(select(Product).where(Product.sku == "LR174890"))
    assert product is not None and product.current_stock == Decimal("3.000")
    # P9/P12: o título nasce na aprovação com o valor acordado e o recebimento parcial não o altera.
    assert purchase.payables[0].amount == Decimal("130.00")

    purchase = cancel_purchase(
        purchase.id,
        PurchaseCancelRequest(
            reason="Fornecedor cancelou o saldo restante", resolution="return_received"
        ),
        db,
        user,
    )

    assert purchase.status == "cancelled"
    assert purchase.items[0].returned_quantity == Decimal("3.000")
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("0.000")
    assert purchase.payables[0].status == "cancelled"
    posted = list(db.scalars(select(StockMovement).order_by(StockMovement.created_at)))
    assert [movement.movement_type for movement in posted] == [
        MovementType.purchase_received,
        MovementType.cancellation,
    ]

    # A repeated cancellation must not return the same goods twice.
    with pytest.raises(HTTPException) as error:
        cancel_purchase(
            purchase.id,
            PurchaseCancelRequest(reason="Repetido", resolution="return_received"),
            db,
            user,
        )
    assert error.value.status_code == 409
    assert db.scalar(select(func.count(StockMovement.id))) == 2


def test_close_balance_keeps_received_goods_and_opens_the_payable(db: Session) -> None:
    user = _actor()
    purchase = _ordered_purchase(db, user)
    line = purchase.items[0]
    purchase = receive_purchase(
        purchase.id,
        PurchaseReceive(
            items=[
                PurchaseReceiveItem(
                    item_id=line.id,
                    receipt_id="receipt-test-close-0001",
                    quantity=2,
                    create_product=True,
                )
            ]
        ),
        db,
        user,
    )
    assert purchase.status == "partially_received"

    purchase = close_purchase_balance(
        purchase.id, PurchaseCloseRequest(reason="Fornecedor não entregou o restante"), db, user
    )

    assert purchase.status == "closed"
    assert purchase.closed_at is not None
    assert db.scalar(select(Product.current_stock).where(Product.sku == "LR174890")) == Decimal("2.000")
    assert purchase.payables[0].amount == Decimal("52.00")

    with pytest.raises(HTTPException) as error:
        close_purchase_balance(purchase.id, PurchaseCloseRequest(reason="De novo"), db, user)
    assert error.value.status_code == 409


def test_expense_payable_is_settled_and_reversed_when_cancelled(db: Session) -> None:
    user = _actor()
    expense = create_purchase(
        PurchaseCreate(
            purchase_type="expense",
            expense_category="Ferramentas",
            expense_amount=Decimal("120.50"),
            supplier_name="Loja X",
            needed_by=datetime(2026, 10, 20, tzinfo=UTC),
            document_date=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        db,
        user,
    )

    assert expense.status == "received"
    assert len(expense.payables) == 1
    payable = expense.payables[0]
    assert payable.amount == Decimal("120.50")
    # P12: despesa sem condição informada vence na data do documento.
    assert payable.due_date.date().isoformat() == "2026-10-05"

    settled = settle_payable(expense.id, payable.id, PayableUpdate(payment_method="Pix"), db, user)
    assert settled.status == "paid"
    assert settled.payment_method == "Pix"

    expense = cancel_purchase(
        expense.id, PurchaseCancelRequest(reason="Despesa lançada por engano"), db, user
    )
    refreshed = get_purchase(expense.id, db, user)
    assert refreshed.status == "cancelled"
    assert refreshed.payables[0].status == "cancelled"


def test_draft_item_without_sku_is_accepted_until_the_order(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[PurchaseItemCreate(description="Peça ainda sem código", quantity=1)]
        ),
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
        purchase.id, line.id, PurchaseItemUpdate(sku="SKU-OK", description="Peça identificada"), db, user
    )
    purchase = place_order(purchase.id, db, user)
    assert purchase.status == "ordered"


def test_draft_lines_can_be_added_and_removed_with_quotes_following(db: Session) -> None:
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=1)]
        ),
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
            item_costs={item.id: Decimal("10") if item.sku == "A" else Decimal("3") for item in purchase.items},
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
    assert purchase.document_date is not None and purchase.document_date.date().isoformat() == "2026-10-01"
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
    """P9, decisão 2A: o documento importado traz os valores do papel e mantém a idempotência."""
    user = _actor()
    payload = PurchaseCreate(
        source_import_id="11111111-2222-3333-4444-555555555555",
        notes="Importação de documento. Total no documento: 100.00",
        items=[
            PurchaseItemCreate(
                sku="DOC-1",
                description="Peça do recibo",
                quantity=2,
                unit_cost=Decimal("50"),
                freight_amount=Decimal("10"),
            )
        ],
    )
    purchase = create_purchase(payload, db, user)
    item = purchase.items[0]

    assert item.base_unit_cost == Decimal("50.00")
    assert item.freight_amount == Decimal("10.00")
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
        PurchaseItemUpdate(
            description="Peça A revisada", quantity=3, base_unit_cost=Decimal("9")
        ),
        db,
        user,
    )
    assert purchase.items[0].quantity == Decimal("3.000")
    assert purchase.items[0].description == "Peça A revisada"
    assert purchase.items[0].base_unit_cost == Decimal("0.00")
    assert purchase.items[0].unit_cost == Decimal("0.00")
    assert purchase.total_amount == Decimal("0.00")


def test_quote_total_must_close_with_the_items(db: Session) -> None:
    """P11: a soma dos itens tem de fechar com o total informado da proposta."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)]),
        db,
        user,
    )
    line = purchase.items[0]
    with pytest.raises(HTTPException) as error:
        add_quote(
            purchase.id,
            PurchaseQuoteCreate(
                supplier_name="Fornecedor", total=99, item_costs={line.id: Decimal("10")}
            ),
            db,
            user,
        )
    assert error.value.status_code == 422
    assert "não fecha" in str(error.value.detail)


def test_quote_below_charges_is_rejected(db: Session) -> None:
    """P11: proposta impossível (total menor que frete + impostos − desconto) não é salva."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=1)]),
        db,
        user,
    )
    line = purchase.items[0]
    with pytest.raises(HTTPException) as error:
        add_quote(
            purchase.id,
            PurchaseQuoteCreate(
                supplier_name="Fornecedor",
                total=10,
                freight_amount=Decimal("50"),
                item_costs={line.id: Decimal("1")},
            ),
            db,
            user,
        )
    assert error.value.status_code == 422
    assert "menor que o frete" in str(error.value.detail)


def test_quote_charges_are_spread_across_items(db: Session) -> None:
    """P11: frete, impostos e desconto da cotação chegam rateados ao item."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            items=[
                PurchaseItemCreate(sku="A", description="Peça A", quantity=1),
                PurchaseItemCreate(sku="B", description="Peça B", quantity=3),
            ]
        ),
        db,
        user,
    )
    lines = purchase.items
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor",
            total=60,
            freight_amount=Decimal("20"),
            item_costs={lines[0].id: Decimal("10"), lines[1].id: Decimal("10")},
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)

    first, second = purchase.items
    assert first.freight_amount == Decimal("5.00")
    assert second.freight_amount == Decimal("15.00")
    assert first.unit_cost == Decimal("15.00")
    assert second.unit_cost == Decimal("15.00")
    assert purchase.total_amount == Decimal("60.00")


def test_selected_quote_can_be_replaced_by_a_new_one(db: Session) -> None:
    """P11: a cotação escolhida não é editada — registra-se outra e escolhe de novo."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)]),
        db,
        user,
    )
    line = purchase.items[0]
    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor A", total=20, item_costs={line.id: Decimal("10")}
        ),
        db,
        user,
    )
    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)
    assert purchase.status == "approved"

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor B", total=16, item_costs={line.id: Decimal("8")}
        ),
        db,
        user,
    )
    replacement = next(quote for quote in purchase.quotes if quote.supplier_name == "Fornecedor B")
    purchase = select_quote(purchase.id, replacement.id, db, user)

    assert len(purchase.quotes) == 2
    assert purchase.items[0].unit_cost == Decimal("8.00")
    assert purchase.total_amount == Decimal("16.00")


def test_approved_quote_creates_the_title_with_the_agreed_condition(db: Session) -> None:
    """P12: o título nasce na aprovação, com o total e a condição da cotação vencedora."""
    user = _actor()
    purchase = create_purchase(
        PurchaseCreate(
            document_date=datetime(2026, 10, 1, tzinfo=UTC),
            items=[PurchaseItemCreate(sku="A", description="Peça A", quantity=2)],
        ),
        db,
        user,
    )
    assert purchase.payables == []
    line = purchase.items[0]

    purchase = add_quote(
        purchase.id,
        PurchaseQuoteCreate(
            supplier_name="Fornecedor",
            total=200,
            item_costs={line.id: Decimal("100")},
            payment_type="installments",
            installment_count=2,
            first_due_days=30,
            interval_days=30,
        ),
        db,
        user,
    )
    assert purchase.payables == []

    purchase = select_quote(purchase.id, purchase.quotes[0].id, db, user)

    payable = purchase.payables[0]
    assert payable.amount == Decimal("200.00")
    assert payable.payment_terms == "30/60"
    assert [item.amount for item in payable.installments] == [
        Decimal("100.00"),
        Decimal("100.00"),
    ]
    assert [item.due_date.date().isoformat() for item in payable.installments] == [
        "2026-10-31",
        "2026-11-30",
    ]
