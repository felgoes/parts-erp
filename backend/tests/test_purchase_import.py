import pytest
from pydantic import ValidationError
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.purchases import create_purchase
from app.models import PurchaseCase, StockMovement
from app.schemas.common import PurchaseCreate, PurchaseImportDocument, PurchaseItemCreate
from app.services.purchase_allocation import ImportPlanError, build_import_plan
from app.services.purchase_import import (
    PROFILE_SCHEMA,
    _extract_items,
    _extract_labeled,
    _money,
    _parse_nfe_xml,
    detect_profile,
    validate_profile,
)


def test_money_parses_brazilian_and_us_decimal_formats():
    assert _money("R$ 1.234,56") == 1234.56
    assert _money("$1,234.56") == 1234.56
    assert _money("42,75") == 42.75


def test_marketplace_profile_detection_requires_evidence_or_manual_choice():
    text = "Mercado Livre\nMercado Pago\nPedido confirmado"
    assert detect_profile(text)["profile_id"] == "mercado_livre"
    # A DANFE without platform branding must remain ambiguous even when the user
    # knows which marketplace originated the purchase.
    assert detect_profile("DANFE\nCNPJ\nValor total da nota")["profile_id"] is None
    assert detect_profile("documento de compra qualquer")["profile_id"] is None
    assert detect_profile("texto sem marca", "amazon")["profile_id"] == "amazon"


def test_weak_profile_and_unlabeled_numbers_are_not_auto_selected():
    assert detect_profile("\\n".join(["Order details", "Total USD 18.00"]))["profile_id"] is None
    fields = _extract_labeled(
        ["Transaction fee 37.03", "Taxable amount 50.31", "28 set, 2026"],
        {"tax": ["tax"], "shipping": ["shipping"], "date": ["date", "order date"]},
    )
    assert fields == {}


def test_labeled_total_and_conservative_item_pattern():
    fields = _extract_labeled(
        ["Order Total: R$ 84,90", "texto aleatório"],
        {"total": ["Order Total"]},
    )
    assert fields["total"]["value"] == 84.90
    items = _extract_items(["Filtro óleo x 2 R$ 42,75 R$ 85,50", "Preço R$ 19,00"])
    assert items == [
        {
            "description": "Filtro óleo",
            "quantity": 2.0,
            "unit_cost": 42.75,
            "line_total": 85.5,
            "confidence": 0.62,
        }
    ]


def test_aliexpress_receipt_labels_localized_date_money_and_multiline_item():
    from app.services.purchase_import import MARKETPLACES, _extract_items

    labels = MARKETPLACES["aliexpress"]["field_labels"]
    fields = _extract_labeled(
        [
            "ID do pedido: ORDER-EXAMPLE",
            "Data do pedido: 28 set, 2026",
            "Subtotal: R$ 214,40",
            "Todos os descontos: R$ 96,71",
            "Custo de frete: R$ 37,03",
            "Impostos: R$ 50,31",
            "Total: R$ 205,03",
        ],
        labels,
    )
    assert fields["order_number"]["value"] == "ORDER-EXAMPLE"
    assert fields["date"]["value"] == "2026-09-28"
    assert fields["subtotal"]["value"] == 214.40
    assert fields["discount"]["value"] == 96.71
    assert fields["shipping"]["value"] == 37.03
    assert fields["tax"]["value"] == 50.31
    assert fields["total"]["value"] == 205.03
    assert _extract_items(
        ["Membrana da tampa da válvula", "10PCS", "BRL 214.40", "x1", "Loja Exemplo"],
        "aliexpress",
    ) == [
        {
            "description": "Membrana da tampa da válvula 10PCS",
            "quantity": 1.0,
            "unit_cost": 214.4,
            "line_total": 214.4,
            "confidence": 0.58,
        }
    ]


def test_alibaba_receipt_labels_currency_and_date_without_using_payment_total():
    from app.services.purchase_import import MARKETPLACES

    fields = _extract_labeled(
        [
            "Sold by: Supplier Example",
            "Receipt number: ORDER-EXAMPLE",
            "Receipt date: 09 Oct, 2026",
            "Subtotal: BRL 1,234.56",
            "Shipping fee: BRL 25.00",
            "Order total: BRL 1,259.56",
            "Payment total: USD 300.00",
        ],
        MARKETPLACES["alibaba"]["field_labels"],
    )
    assert fields["supplier"]["value"] == "Supplier Example"
    assert fields["order_number"]["value"] == "ORDER-EXAMPLE"
    assert fields["date"]["value"] == "2026-10-09"
    assert fields["subtotal"]["value"] == 1234.56
    assert fields["shipping"]["value"] == 25.0
    assert fields["total"]["value"] == 1259.56
    assert _money("BRL 1,234.56") == 1234.56
    assert _money("USD 1,234.56") == 1234.56


def test_blank_sku_is_allowed_in_drafts_and_required_before_the_order():
    line = PurchaseItemCreate(description="Filtro", quantity=1, unit_cost=10)
    draft = PurchaseCreate(purchase_type="parts", items=[line])
    assert draft.items[0].sku == ""
    imported = PurchaseCreate(
        purchase_type="parts",
        notes="Importação de documento. Documento revisado pelo usuário.",
        items=[line],
    )
    assert imported.items[0].sku == ""


def test_custom_profile_has_limited_declarative_schema():
    clean = validate_profile(
        {
            "schema": PROFILE_SCHEMA,
            "profile_id": "loja_exemplo",
            "name": "Minha loja",
            "version": 1,
            "match_terms": ["Minha loja"],
            "field_labels": {"total": ["Total pago"]},
        }
    )
    assert clean["profile_id"] == "loja_exemplo"
    with pytest.raises(ValueError, match="propriedades não permitidas"):
        validate_profile({**clean, "script": "import os"})


def test_nfe_xml_reads_supplier_items_and_total():
    xml = b"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe><infNFe><emit><CNPJ>04617659000142</CNPJ><xNome>Fornecedor Exemplo</xNome></emit>
      <det nItem="1"><prod><cProd>A-1</cProd><xProd>Filtro oleo</xProd><qCom>2.0000</qCom>
      <vUnCom>10.5000</vUnCom><vProd>21.00</vProd></prod></det>
      <ide><nNF>219</nNF><serie>2</serie><dhEmi>2026-10-09T10:30:00-03:00</dhEmi></ide>
      <total><ICMSTot><vFrete>2.00</vFrete><vDesc>1.00</vDesc><vTotTrib>3.00</vTotTrib><vNF>21.00</vNF></ICMSTot></total></infNFe></NFe>
      <protNFe><infProt><chNFe>12345678901234567890123456789012345678901234</chNFe></infProt></protNFe>
    </nfeProc>"""
    parsed = _parse_nfe_xml(xml)
    assert parsed["fields"]["supplier"]["value"] == "Fornecedor Exemplo"
    assert parsed["fields"]["total"]["value"] == 21.0
    assert parsed["fields"]["date"]["value"] == "2026-10-09"
    assert parsed["fields"]["shipping"]["value"] == 2.0
    assert parsed["fields"]["discount"]["value"] == 1.0
    assert parsed["fields"]["tax"]["value"] == 3.0
    assert parsed["items"][0]["sku"] == "A-1"
    assert parsed["items"][0]["quantity"] == 2
    # P14: identidade do documento fiscal em campos próprios.
    assert parsed["fields"]["access_key"]["value"] == "12345678901234567890123456789012345678901234"
    assert parsed["fields"]["document_number"]["value"] == "219"
    assert parsed["fields"]["document_series"]["value"] == "2"
    assert parsed["fields"]["issuer_cnpj"]["value"] == "04617659000142"


# --- P0: a compra importada nasce com a cotação do documento aceita e o pedido registrado ---


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
    for item, line in zip(purchase.items, plan.lines):
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
        item.id: line.base_unit_cost for item, line in zip(purchase.items, plan.lines)
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
