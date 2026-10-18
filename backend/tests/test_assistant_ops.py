from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.assistant import tool_ops
from app.models import (
    Customer,
    InvoiceItem,
    InvoiceSource,
    InvoiceStatus,
    MarketplaceOrder,
    MovementType,
    Product,
    PurchaseCase,
    PurchasePayable,
    SalesInvoice,
    StockMovement,
)


def seed_operation(db) -> Product:
    customer = Customer(
        name="Ana Cliente",
        document="12345678900",
        email="ana@example.test",
        phone="11999998888",
    )
    product = Product(
        sku="OPS-1",
        name="Filtro operacional",
        current_stock=1,
        minimum_stock=5,
        sale_price=50,
    )
    db.add_all([customer, product])
    db.commit()
    invoice = SalesInvoice(
        number="VEN-100",
        status=InvoiceStatus.confirmed,
        source=InvoiceSource.mercadolivre,
        marketplace_order_id="ML-100",
        customer_id=customer.id,
        subtotal=Decimal("50"),
        total=Decimal("50"),
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    db.commit()
    db.add_all(
        [
            InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                sku=product.sku,
                description=product.name,
                quantity=Decimal("1"),
                unit_price=Decimal("50"),
                total=Decimal("50"),
            ),
            MarketplaceOrder(
                provider="mercadolivre",
                external_order_id="ML-100",
                seller_id="seller",
                status="paid",
                invoice_id=invoice.id,
                shipping_status="ready_to_ship",
                shipping_substatus="ready_to_print",
                label_status="ready",
                fiscal_status="error",
                fiscal_error="falha sk-SECRET12345 contato ana@example.test",
                payload={},
            ),
            StockMovement(
                product_id=product.id,
                movement_type=MovementType.adjustment,
                quantity=Decimal("-1"),
                balance_after=Decimal("1"),
                reason="Avaria",
                idempotency_key="ops-1",
            ),
        ]
    )
    purchase = PurchaseCase(number="COM-OPS-1", status="received")
    db.add(purchase)
    db.commit()
    db.add(
        PurchasePayable(
            purchase_id=purchase.id,
            supplier_name="Fornecedor",
            amount=Decimal("100"),
            paid_amount=Decimal("20"),
            due_date=datetime.now(UTC) - timedelta(days=5),
            status="open",
        )
    )
    db.commit()
    return product


def test_operational_summary_counts_actionable_items(db):
    seed_operation(db)
    summary = tool_ops.resumo_operacional(db)
    assert summary["vendas_hoje"] == {"quantidade": 1, "total": "50.00"}
    assert summary["pedidos_prontos_para_envio"] == 1
    assert summary["erros_fiscais"] == 1
    assert summary["produtos_abaixo_do_minimo"] == 1
    assert summary["contas_vencidas"] == {"quantidade": 1, "saldo": "80.00"}


def test_overdue_payables_and_customer_privacy(db):
    seed_operation(db)
    payables = tool_ops.listar_contas_a_pagar(db, vencidas=True)
    assert payables["total"] == 1
    assert payables["saldo_total"] == "80.00"
    assert payables["contas"][0]["dias_em_atraso"] >= 4

    customers = tool_ops.buscar_clientes(db, "Ana")
    assert customers["clientes"][0]["nome"] == "Ana Cliente"
    assert customers["clientes"][0]["email"] == "a***@example.test"
    assert customers["clientes"][0]["documento"] == "***8900"
    assert customers["clientes"][0]["telefone"] == "***8888"
    assert customers["clientes"][0]["total_comprado"] == "50.00"


def test_stock_movements_and_sale_detail_redact_secrets(db):
    seed_operation(db)
    movements = tool_ops.movimentacoes_estoque(db, "OPS-1")
    assert movements["movimentacoes"][0]["sku"] == "OPS-1"
    assert movements["movimentacoes"][0]["tipo"] == "adjustment"
    assert movements["movimentacoes"][0]["saldo_apos"] == "1.000"

    detail = tool_ops.detalhar_venda(db, "VEN-100")
    assert detail["cliente"] == "Ana Cliente"
    assert detail["itens"][0]["sku"] == "OPS-1"
    assert detail["envio"]["status_envio"] == "ready_to_ship"
    assert detail["fiscal"]["status"] == "error"
    assert "sk-SECRET" not in str(detail)
    assert "ana@example.test" not in str(detail)

    errors = tool_ops.listar_erros_fiscais(db)
    assert errors["total"] == 1
    assert "sk-SECRET" not in str(errors)
