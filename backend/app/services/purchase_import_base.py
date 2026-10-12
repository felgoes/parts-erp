"""Constantes da leitura de documento de compra: perfis, rótulos, padrões e limites."""

import re
import threading
from typing import Any

PROFILE_SCHEMA = "parts-erp-purchase-import-profile/v1"
MAX_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 10
MARKETPLACES: dict[str, dict[str, Any]] = {
    "aliexpress": {
        "name": "AliExpress",
        "terms": ["aliexpress"],
        "field_labels": {
            "order_number": ["id do pedido", "order id"],
            "date": ["data do pedido", "order date"],
            "subtotal": ["subtotal"],
            "total": ["total", "order total", "total paid", "total do pedido", "valor total"],
            "shipping": ["custo de frete", "shipping fee", "frete", "delivery fee"],
            "discount": ["todos os descontos", "coupon", "discount", "desconto"],
            "tax": ["impostos", "taxes", "tax"],
            "paid": ["você pagou", "voce pagou", "total pago", "amount paid"],
        },
    },
    "mercado_livre": {
        "name": "Mercado Livre",
        "terms": ["mercado livre", "mercadolivre", "meli", "mercadolibre"],
        "field_labels": {
            "supplier": ["vendedor", "loja", "seller"],
            "order_number": ["número da compra", "número do pedido", "pedido nº"],
            "total": ["total da compra", "total pago", "valor total"],
        },
    },
    "shopee": {
        "name": "Shopee",
        "terms": ["shopee", "spaylater", "pedido shopee"],
        "field_labels": {
            "supplier": ["loja", "seller"],
            "order_number": ["id do pedido", "order id"],
            "total": ["total do pedido", "total pago", "valor total"],
            "shipping": ["taxa de envio", "frete"],
            "discount": ["desconto da loja", "cupom"],
        },
    },
    "amazon": {
        "name": "Amazon",
        "terms": ["amazon", "amazon.com.br"],
        "field_labels": {
            "supplier": ["sold by", "vendido por"],
            "order_number": ["order number", "número do pedido"],
            "total": ["order total", "total do pedido"],
            "shipping": ["shipping & handling", "frete e manuseio"],
        },
    },
    "alibaba": {
        "name": "Alibaba",
        "terms": ["alibaba.com", "trade assurance", "alibaba group"],
        "field_labels": {
            "supplier": ["sold by", "supplier", "seller"],
            "order_number": ["receipt number", "order number", "trade order"],
            "date": ["receipt date", "order date"],
            "subtotal": ["subtotal"],
            "total": ["order total"],
            "shipping": ["shipping fee", "shipping cost", "freight"],
            "paid": ["amount paid", "payment total"],
        },
    },
}
FIELD_LABELS: dict[str, list[str]] = {
    "supplier": ["seller", "sold by", "fornecedor", "vendido por", "loja"],
    "order_number": [
        "order number",
        "order id",
        "id do pedido",
        "número do pedido",
        "pedido nº",
        "pedido no",
    ],
    "date": ["receipt date", "order date", "purchase date", "data do pedido", "data da compra"],
    "subtotal": ["subtotal", "item subtotal", "subtotal dos produtos"],
    "shipping": ["shipping fee", "shipping", "frete", "delivery fee", "custo de frete"],
    "discount": ["todos os descontos", "discount", "desconto", "coupon"],
    "total": ["order total", "total do pedido", "total pago", "valor total", "total"],
    "tax": ["tax", "taxes", "taxa", "imposto", "impostos", "vat", "iva"],
}
MONEY = r"(?:(?:R\$|BRL|USD|US\$|\$)\s*)?-?\s*(?:\d{1,3}(?:[,.]\d{3})+|\d+)(?:,\d{2}|\.\d{2})"
DATE_PATTERN = (
    r"(\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:de\s+)?[a-z]{3,12}\.?,?\s+(?:de\s+)?\d{4}"
    r"|[a-z]{3,12}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"
)
_OCR_SLOT = threading.BoundedSemaphore(1)
LABEL_ARTIFACT = (
    "address",
    "ship to",
    "endereco",
    "telefone",
    "phone",
    "email",
    "cnpj",
    "date",
    "data",
    "number",
    "numero",
    "total",
    "qty",
    "quantity",
    "unit price",
    "price",
    "tax",
)
QUANTITY_HINT = re.compile(r"\bx\s*(\d+)\b|\bqty\s*:?\s*(\d+)\b|\b(\d+)\s*un\b", re.I)
CELL_SPLIT = re.compile(r"\s{2,}")
NUMBER_CELL = re.compile(r"^(?:R\$|BRL|USD|US\$|\$)?\s*-?\d+(?:[.,]\d{1,2})?$", re.I)
DANFE_VALUE_COLUMNS = {
    "subtotal": "VALOR TOTAL DOS PRODUTOS",
    "shipping": "VALOR DO FRETE",
    "discount": "DESCONTO",
    "total": "VALOR TOTAL DA NOTA",
    "date": "DATA DA EMISSÃO",
}
