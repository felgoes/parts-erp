from decimal import Decimal

from app.assistant import tool_reads
from app.models import (
    InvoiceSource,
    InvoiceStatus,
    MarketplaceOrder,
    SalesInvoice,
)


def test_sales_list_finds_orders_ready_to_ship(db):
    invoice = SalesInvoice(
        number="VEN-10",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.mercadolivre,
        marketplace_order_id="ML-10",
        total=Decimal("80.00"),
    )
    db.add(invoice)
    db.commit()
    db.add_all(
        [
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id="ML-10",
                seller_id="seller",
                status="paid",
                invoice_id=invoice.id,
                shipping_status="ready_to_ship",
                shipping_substatus="ready_to_print",
                label_status="ready",
                fiscal_status="authorized",
                payload={},
            ),
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id="ML-11",
                seller_id="seller",
                status="paid",
                shipping_status="shipped",
                label_status="downloaded",
                fiscal_status="authorized",
                payload={},
            ),
        ]
    )
    db.commit()

    ready = tool_reads.listar_vendas(db, pendentes_envio=True)
    assert ready["total"] == 1
    assert ready["vendas"][0]["pedido"] == "ML-10"
    assert ready["vendas"][0]["fatura"] == "VEN-10"
    assert ready["vendas"][0]["status_envio"] == "ready_to_ship"

    everything = tool_reads.listar_vendas(db)
    assert everything["total"] == 2
    assert {row["pedido"] for row in everything["vendas"]} == {"ML-10", "ML-11"}
