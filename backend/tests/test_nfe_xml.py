"""S5 — a leitura do XML da NF-e recusa DTD e entidades antes de interpretar o conteúdo."""

import pytest

from app.services.nfe_xml import parse_nfe_xml

MINIMAL_NFE = b"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe><emit><xNome>Fornecedor</xNome></emit><ide><nNF>7</nNF></ide>
  <total><ICMSTot><vNF>10.00</vNF></ICMSTot></total></infNFe></NFe>
</nfeProc>"""


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE nfe [<!ENTITY riso "hahaha">]><nfe/>',
        b"<nfe>&riso;</nfe>",
        b'<?xml version="1.0"?><!DOCTYPE nfe SYSTEM "file:///etc/passwd"><nfe/>',
    ],
)
def test_xml_with_external_declarations_is_refused(payload: bytes) -> None:
    with pytest.raises(ValueError, match="declarações externas"):
        parse_nfe_xml(payload)


def test_malformed_xml_becomes_a_clear_error() -> None:
    with pytest.raises(ValueError, match="não é aceito"):
        parse_nfe_xml(b"<nfe><nao-fechado>")


def test_minimal_nfe_is_still_read() -> None:
    parsed = parse_nfe_xml(MINIMAL_NFE)
    assert parsed["fields"]["supplier"]["value"] == "Fornecedor"
    assert parsed["fields"]["document_number"]["value"] == "7"
    assert parsed["items"] == []
