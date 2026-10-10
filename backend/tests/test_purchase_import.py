import pytest
from pydantic import ValidationError

from app.schemas.common import PurchaseCreate, PurchaseItemCreate
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


def test_blank_sku_is_allowed_only_for_reviewed_document_imports():
    line = PurchaseItemCreate(description="Filtro", quantity=1, unit_cost=10)
    with pytest.raises(ValidationError, match="Informe o SKU"):
        PurchaseCreate(purchase_type="parts", items=[line])
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
      <NFe><infNFe><emit><xNome>Fornecedor Exemplo</xNome></emit>
      <det nItem="1"><prod><cProd>A-1</cProd><xProd>Filtro oleo</xProd><qCom>2.0000</qCom>
      <vUnCom>10.5000</vUnCom><vProd>21.00</vProd></prod></det>
      <ide><dhEmi>2026-10-09T10:30:00-03:00</dhEmi></ide>
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
