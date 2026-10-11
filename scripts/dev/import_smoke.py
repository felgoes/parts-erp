#!/usr/bin/env python3
"""Smoke do fluxo de importação de compra contra o HML local.

Cobre o caminho entregue pela P0: o documento importado vira compra feita — cotação do
documento aceita, pedido registrado e título a pagar — e o recebimento parcial funciona
logo depois, com o custo final da peça vindo do rateio do documento.

Roda sempre contra o HML local (API em `http://127.0.0.1:8000`) e o banco de QA; nunca
aponte para produção. Uso:

    cd ~/workspace/garagista/parts-erp-main
    ./scripts/hml-local.sh start
    ./backend/.venv/bin/python scripts/dev/import_smoke.py
    ./scripts/hml-local.sh stop

Nenhuma credencial é impressa: a conta de QA é lida do `.env.qa.local` ignorado.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env.qa.local"
BASE_URL = os.environ.get("PARTS_ERP_API_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api/v1"

# Valores do documento de amostra (nota de peças): 3 × 20,00 + 2 × 25,00 = 110,00
# mais frete 5,00 e impostos 4,00 menos desconto 2,00 = 117,00.
DOCUMENT_TOTAL = 117.00
DOCUMENT_DATE = "2026-10-09"
EXPECTED_DUE_DATE = (datetime(2026, 10, 9, tzinfo=UTC) + timedelta(days=30)).date().isoformat()

failures: list[str] = []


def ok(label: str) -> None:
    print(f"  ok      {label}")


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        ok(label)
        return
    failures.append(label)
    print(f"  FALHOU  {label}{f' — {detail}' if detail else ''}")


def qa_credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        raw = raw.strip()
        if raw.startswith(("'", '"')):
            raw = ast.literal_eval(raw)
        values[key.strip()] = raw
    missing = {"BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD"} - values.keys()
    if missing:
        raise SystemExit(f"Faltam chaves no .env.qa.local: {', '.join(sorted(missing))}")
    return values["BOOTSTRAP_ADMIN_EMAIL"], values["BOOTSTRAP_ADMIN_PASSWORD"]


def sample_document() -> bytes:
    """NF-e de amostra com identificadores únicos, para repetir o smoke sem bater no bloqueio de duplicidade."""
    number = datetime.now(UTC).strftime("%H%M%S")
    access_key = f"352610{uuid.uuid4().int % 10**32:032d}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe{access_key}">
      <ide><nNF>{number}</nNF><dhEmi>{DOCUMENT_DATE}T08:40:00-03:00</dhEmi></ide>
      <emit><xNome>Distribuidora Exemplo de Autopecas</xNome></emit>
      <det nItem="1"><prod><cProd>SMOKE-1</cProd><xProd>Correia dentada</xProd>
        <qCom>3.0000</qCom><vUnCom>20.0000</vUnCom><vProd>60.00</vProd></prod></det>
      <det nItem="2"><prod><cProd>SMOKE-2</cProd><xProd>Vela de ignicao</xProd>
        <qCom>2.0000</qCom><vUnCom>25.0000</vUnCom><vProd>50.00</vProd></prod></det>
      <total><ICMSTot><vFrete>5.00</vFrete><vDesc>2.00</vDesc><vTotTrib>4.00</vTotTrib>
        <vNF>{DOCUMENT_TOTAL:.2f}</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><chNFe>{access_key}</chNFe></infProt></protNFe>
</nfeProc>
""".encode()


def main() -> int:
    email, password = qa_credentials()
    with httpx.Client(timeout=30) as client:
        login = client.post(f"{API}/auth/login", data={"username": email, "password": password})
        if login.status_code != 200:
            raise SystemExit(f"Login de QA falhou (HTTP {login.status_code}). O HML local está de pé?")
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        ok("login de QA no HML local")

        review_response = client.post(
            f"{API}/purchases/import-document",
            files={"file": ("smoke-nfe.xml", sample_document(), "application/xml")},
        )
        check("documento analisado", review_response.status_code == 200, review_response.text[:200])
        review = review_response.json()
        fields = review.get("fields", {})
        items = review.get("items", [])
        check("dois itens lidos do documento", len(items) == 2, f"{len(items)} itens")
        check(
            "total lido bate com o documento",
            float(fields.get("total", {}).get("value", 0)) == DOCUMENT_TOTAL,
            str(fields.get("total", {}).get("value")),
        )

        import_id = str(uuid.uuid4())
        payload = {
            "purchase_type": "parts",
            "source_import_id": import_id,
            "supplier_name": fields.get("supplier", {}).get("value"),
            "document_date": fields.get("date", {}).get("value"),
            "notes": "Importação de documento. Smoke automático do fluxo de importação.",
            "import_document": {
                "filename": "smoke-nfe.xml",
                "total": float(fields["total"]["value"]),
                "freight_amount": float(fields.get("shipping", {}).get("value") or 0),
                "tax_amount": float(fields.get("tax", {}).get("value") or 0),
                "discount_amount": float(fields.get("discount", {}).get("value") or 0),
            },
            "items": [
                {
                    "sku": item.get("sku") or "",
                    "description": item["description"],
                    "quantity": float(item["quantity"]),
                    "unit_cost": float(item["unit_cost"]),
                    "line_discount_amount": float(item.get("discount_amount") or 0),
                }
                for item in items
            ],
        }
        created_response = client.post(f"{API}/purchases", json=payload)
        check("compra criada", created_response.status_code == 201, created_response.text[:300])
        purchase = created_response.json()
        check("compra nasce com o pedido registrado", purchase.get("status") == "ordered", str(purchase.get("status")))
        check("cotação escolhida gravada", bool(purchase.get("selected_quote_id")))
        quotes = purchase.get("quotes") or []
        check(
            "cotação do documento é a vencedora",
            len(quotes) == 1 and float(quotes[0]["total"]) == DOCUMENT_TOTAL,
            json.dumps([q.get("total") for q in quotes]),
        )
        check(
            "cotação registrada com a nota do documento",
            "Cotação do documento importado" in str(quotes[0].get("notes") if quotes else ""),
        )
        payables = purchase.get("payables") or []
        check("título a pagar criado", len(payables) == 1, f"{len(payables)} título(s)")
        if payables:
            payable = payables[0]
            check("título com o valor da cotação", float(payable["amount"]) == DOCUMENT_TOTAL, str(payable["amount"]))
            check(
                "vencimento em 30 dias da data do documento",
                str(payable["due_date"])[:10] == EXPECTED_DUE_DATE,
                str(payable["due_date"]),
            )
        items_out = purchase.get("items") or []
        closing = sum(
            float(item["quantity"]) * float(item["unit_cost"]) for item in items_out
        )
        check(
            "soma dos itens fecha com o total do documento",
            abs(closing - DOCUMENT_TOTAL) <= 0.01 * len(items_out),
            f"{closing:.2f} vs {DOCUMENT_TOTAL:.2f}",
        )
        check(
            "custo final por peça maior que o custo base",
            all(float(item["unit_cost"]) >= float(item["base_unit_cost"]) for item in items_out),
        )

        repeatedly = client.post(f"{API}/purchases", json=payload)
        check(
            "repetir a confirmação devolve a mesma compra",
            repeatedly.status_code == 201 and repeatedly.json()["id"] == purchase["id"],
            repeatedly.text[:200],
        )

        first_item = items_out[0]
        received = client.post(
            f"{API}/purchases/{purchase['id']}/receive",
            json={
                "items": [
                    {
                        "item_id": first_item["id"],
                        "receipt_id": uuid.uuid4().hex[:24],
                        "quantity": 1,
                        "create_product": True,
                    }
                ]
            },
        )
        check("recebimento parcial aceito", received.status_code == 200, received.text[:300])
        if received.status_code == 200:
            after = received.json()
            check("compra fica em recebimento parcial", after["status"] == "partially_received", after["status"])
            check(
                "quantidade recebida registrada",
                float(after["items"][0]["received_quantity"]) == 1,
                str(after["items"][0]["received_quantity"]),
            )

    if failures:
        print(f"\nsmoke do fluxo de importação REPROVOU em {len(failures)} verificação(ões).")
        return 1
    print("\nsmoke do fluxo de importação ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
