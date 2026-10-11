"""P14 — leitura de itens por coluna (recibos de marketplace e DANFE)."""

from app.services.purchase_import import (
    _extract_danfe_fields,
    _extract_danfe_items,
    _extract_items_by_columns,
    _looks_like_danfe,
)


def test_column_grid_reads_quantity_unit_and_line_total():
    lines = [
        "Receipt number: #312403958001029344",
        "Auto Parts Engine Coolant Temperature Sensor &amp; Connector D4G15B-3611043    20.00    BRL 6.43    BRL 128.42",
    ]

    items = _extract_items_by_columns(lines)

    assert len(items) == 1
    item = items[0]
    assert item["description"].startswith("Auto Parts Engine Coolant Temperature Sensor")
    assert "&amp;" not in item["description"]
    assert item["quantity"] == 20.0
    assert item["unit_cost"] == 6.43
    assert item["line_total"] == 128.42
    assert item["source"] == "columns"


def test_column_grid_derives_quantity_when_only_unit_and_total_are_read():
    items = _extract_items_by_columns(
        ["Fita de empacotamento 45mm    5,00    25,00"]
    )

    assert len(items) == 1
    assert items[0]["quantity"] == 5.0
    assert items[0]["quantity_derived"] is True


def test_danfe_reads_document_identity_and_item_with_two_line_description():
    lines = [
        "RECEBEMOS DE STARHOUSE MEGA STORE LTDA OS PRODUTOS CONSTANTES DA NOTA FISCAL INDICADA AO LADO",
        "CHAVE DE ACESSO",
        "3526 0904 6176 5900 0142 5500 2003 1786 5516 5579 9260",
        "SÉRIE 002",
        "Nº    003.178.655",
        "CNPJ 04.617.659/0001-42",
        "VALOR TOTAL DOS PRODUTOS    VALOR DO FRETE    DESCONTO    VALOR TOTAL DA NOTA",
        "29,90    0,00    0,00    29,90",
        "DATA DA EMISSÃO",
        "25/09/2026",
        "CÓDIGO    DESCRIÇAO DOS PRODUTOS / SERVIÇOS    UNID.    QTD.    VLR UNIT.    VALOR TOTAL",
        "Fita De Empacotamento 3m Scotch 5802 45mm X",
        "175461    39191010    000    5106    UN    1    29,90    29,90    29,90",
        "45m 4 Rolos",
    ]

    assert _looks_like_danfe(lines) is True
    fields = _extract_danfe_fields(lines)
    assert fields["access_key"]["value"] == "35260904617659000142550020031786551655799260"
    assert fields["supplier"]["value"] == "STARHOUSE MEGA STORE LTDA"
    assert fields["document_number"]["value"] == "003.178.655"
    assert fields["document_series"]["value"] == "002"
    assert fields["issuer_cnpj"]["value"] == "04.617.659/0001-42"
    assert fields["date"]["value"] == "2026-09-25"
    assert fields["subtotal"]["value"] == 29.9
    assert fields["shipping"]["value"] == 0.0
    assert fields["total"]["value"] == 29.9

    items = _extract_danfe_items(lines)
    assert len(items) == 1
    assert items[0]["description"] == "Fita De Empacotamento 3m Scotch 5802 45mm X 45m 4 Rolos"
    assert items[0]["sku"] == "175461"
    assert items[0]["unit"] == "UN"
    assert items[0]["quantity"] == 1.0
    assert items[0]["unit_cost"] == 29.9
    assert items[0]["line_total"] == 29.9
