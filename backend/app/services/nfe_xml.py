"""Leitura do XML da NF-e, com parser endurecido.

Separado da importação de compra para a leitura do documento ter um módulo próprio e o
arquivo da importação não crescer. Usa `defusedxml`: DTD, entidades e referências externas
são recusadas antes de qualquer interpretação do conteúdo.
"""

from typing import Any
from xml.etree.ElementTree import Element, ParseError

import defusedxml.ElementTree as safe_etree
from defusedxml.common import DefusedXmlException


def parse_nfe_xml(data: bytes) -> dict[str, Any]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML com declarações externas não é aceito.")
    try:
        # Parser endurecido (defusedxml): recusa DTD, entidades e referências externas.
        root = safe_etree.fromstring(data)
    except (DefusedXmlException, ParseError, ValueError) as exc:
        raise ValueError("XML inválido ou com declarações externas não é aceito.") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def one(name: str, within: Element | None = None) -> str | None:
        # `within is None` (e não `within or root`): um elemento vazio é falsy, e a busca
        # precisa ficar dentro dele quando ele foi informado.
        parent = root if within is None else within
        node = next((n for n in parent.iter() if local(n.tag) == name), None)
        return node.text.strip() if node is not None and node.text else None

    supplier = one("xNome")
    access = one("chNFe")
    if not access:
        inf = next((node for node in root.iter() if local(node.tag) == "infNFe"), None)
        if inf is not None:
            identity = inf.attrib.get("Id", "")
            access = identity[3:] if identity.startswith("NFe") else None
    number = one("nNF")
    total = one("vNF")
    issue_date = one("dhEmi") or one("dEmi")
    freight = one("vFrete")
    discount = one("vDesc")
    tax = one("vTotTrib")
    items = []
    for det in (n for n in root.iter() if local(n.tag) == "det"):
        prod = next((n for n in det if local(n.tag) == "prod"), None)
        if prod is None:
            continue
        vals = {local(n.tag): n.text.strip() for n in prod if n.text}
        try:
            items.append(
                {
                    "description": vals.get("xProd", "")[:200],
                    "sku": vals.get("cProd", "")[:80],
                    "quantity": float(vals.get("qCom", "0")),
                    "unit_cost": round(float(vals.get("vUnCom", "0")), 4),
                    "line_total": max(
                        0,
                        round(float(vals.get("vProd", "0")) - float(one("vDesc", det) or "0"), 2),
                    ),
                    "discount_amount": round(float(one("vDesc", det) or "0"), 2),
                    "confidence": 1.0,
                }
            )
        except ValueError:
            continue
    fields = {}
    if supplier:
        fields["supplier"] = {"value": supplier, "confidence": 1.0, "source": "xml"}
    if number:
        fields["order_number"] = {"value": number, "confidence": 1.0, "source": "xml"}
    if total:
        fields["total"] = {"value": round(float(total), 2), "confidence": 1.0, "source": "xml"}
    if access:
        fields["access_key"] = {"value": access, "confidence": 1.0, "source": "xml"}
    if issue_date:
        fields["date"] = {"value": issue_date[:10], "confidence": 1.0, "source": "xml"}
    issuer_cnpj = one("CNPJ")
    series = one("serie")
    if issuer_cnpj:
        fields["issuer_cnpj"] = {"value": issuer_cnpj, "confidence": 1.0, "source": "xml"}
    if series:
        fields["document_series"] = {"value": series, "confidence": 1.0, "source": "xml"}
    if number:
        fields["document_number"] = {"value": number, "confidence": 1.0, "source": "xml"}
    for field, value in (("shipping", freight), ("discount", discount), ("tax", tax)):
        if value:
            fields[field] = {"value": round(float(value), 2), "confidence": 1.0, "source": "xml"}
    return {"fields": fields, "items": items, "warnings": []}
