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
