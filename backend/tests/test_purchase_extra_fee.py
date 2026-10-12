"""P5 — taxa extra (pagamento/processamento) na cotação, na importação e na compra."""

from decimal import Decimal

import pytest

from app.api.routes.purchases_support import _recompute_purchase_costs
from app.models import PurchaseCase, PurchaseItem, PurchaseQuote
from app.services.purchase_allocation import ImportPlanError, build_import_plan
from app.services.purchase_import import _extract_labeled, _profile_labels


def test_extra_fee_enters_the_closing_and_the_final_unit_cost():
    """Documento do AliExpress: pedido 310,34 + taxa 9,31 = pago 319,65."""
    plan = build_import_plan(
        [(Decimal("2"), Decimal("155.17"), Decimal("0"))],
        extras_amount=Decimal("9.31"),
        document_total=Decimal("319.65"),
    )

    assert plan.extras_amount == Decimal("9.31")
    assert plan.items_subtotal == Decimal("310.34")
    assert plan.total == Decimal("319.65")
    assert plan.difference == Decimal("0.00")
    # O custo final da peça carrega a taxa: 155,17 + 4,655 → 159,83 por unidade.
    assert plan.lines[0].base_unit_cost == Decimal("155.17")
    assert plan.lines[0].extras_amount == Decimal("9.31")
    assert plan.lines[0].unit_cost == Decimal("159.83")


def test_extra_fee_is_shared_exactly_with_the_cent_left_on_the_largest_item():
    """O rateio fecha centavo a centavo: a sobra fica no item de maior valor."""
    plan = build_import_plan(
        [
            (Decimal("1"), Decimal("30.00"), Decimal("0")),
            (Decimal("1"), Decimal("70.00"), Decimal("0")),
            (Decimal("1"), Decimal("0.01"), Decimal("0")),
        ],
        extras_amount=Decimal("10.00"),
    )

    assert sum(line.extras_amount for line in plan.lines) == Decimal("10.00")
    assert plan.lines[1].extras_amount > plan.lines[0].extras_amount > plan.lines[2].extras_amount
    assert plan.computed_total == Decimal("110.01")


def test_fee_plus_freight_and_tax_above_the_document_total_is_refused():
    with pytest.raises(ImportPlanError, match="superam o total"):
        build_import_plan(
            [(Decimal("1"), Decimal("10.00"), Decimal("0"))],
            freight_amount=Decimal("5.00"),
            extras_amount=Decimal("8.00"),
            document_total=Decimal("11.00"),
        )


def test_printed_line_total_wins_over_the_recalculated_unit_price():
    """Recibo do Alibaba: 20 × 6,43 = 128,60, mas o papel cobra 128,42 pela linha.

    Sem respeitar o total impresso, o fechamento acusava R$ 0,18 de diferença e a importação
    ficava bloqueada num documento que fecha.
    """
    plan = build_import_plan(
        [(Decimal("20"), Decimal("6.43"), Decimal("0"), Decimal("128.42"))],
        freight_amount=Decimal("181.92"),
        extras_amount=Decimal("9.31"),
        document_total=Decimal("319.65"),
    )

    assert plan.items_subtotal == Decimal("128.42")
    assert plan.computed_total == Decimal("319.65")
    assert plan.difference == Decimal("0.00")
    assert plan.total == Decimal("319.65")
    # O custo final por peça: base da linha (128,42 / 20 = 6,42) mais frete e taxa rateados
    # (191,23 / 20 = 9,56).
    assert plan.lines[0].base_unit_cost == Decimal("6.42")
    assert plan.lines[0].unit_cost == Decimal("15.98")


def test_line_without_printed_total_keeps_the_recalculated_value():
    plan = build_import_plan([(Decimal("2"), Decimal("10.00"), Decimal("0"))])
    assert plan.items_subtotal == Decimal("20.00")


def test_portuguese_payment_fee_is_not_read_as_tax():
    """P5: "taxa de pagamento" vence o rótulo genérico "taxa" de imposto."""
    lines = [
        "Order total BRL 310,34",
        "Payment processing fee BRL 9,31",
        "Amount paid BRL 319,65",
    ]
    fields = _extract_labeled(lines, _profile_labels("aliexpress"))

    assert fields["extras"]["value"] == 9.31
    assert "tax" not in fields

    portuguese = ["Total do pedido R$ 310,34", "Taxa de pagamento R$ 9,31"]
    parsed = _extract_labeled(portuguese, _profile_labels("aliexpress"))
    assert parsed["extras"]["value"] == 9.31
    assert "tax" not in parsed


def test_generic_tax_label_still_reads_impostos():
    parsed = _extract_labeled(
        ["Impostos R$ 4,00", "Total do pedido R$ 100,00"], _profile_labels("aliexpress")
    )
    assert parsed["tax"]["value"] == 4.0
    assert "extras" not in parsed


def test_winning_quote_with_fee_lands_in_the_item_cost(db):
    """Ao escolher a cotação, a taxa entra no custo final de cada peça."""
    purchase = PurchaseCase(
        number="COM-P5-1",
        status="negotiating",
        purchase_type="parts",
        supplier_name="Fornecedor Teste",
        items=[
            PurchaseItem(sku="A", description="Peça A", quantity=Decimal("1"), unit="un"),
            PurchaseItem(sku="B", description="Peça B", quantity=Decimal("1"), unit="un"),
        ],
    )
    db.add(purchase)
    db.flush()
    quote = PurchaseQuote(
        purchase_id=purchase.id,
        supplier_name="Fornecedor Teste",
        total=Decimal("109.31"),
        freight_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        extras_amount=Decimal("9.31"),
        discount_amount=Decimal("0"),
        allocation_method="proportional",
        item_costs={purchase.items[0].id: "30.00", purchase.items[1].id: "70.00"},
    )
    purchase.quotes.append(quote)
    db.flush()

    _recompute_purchase_costs(purchase, quote)

    first, second = purchase.items
    assert first.base_unit_cost == Decimal("30.00")
    assert first.extras_amount == Decimal("2.79")
    assert first.unit_cost == Decimal("32.79")
    assert second.extras_amount == Decimal("6.52")
    assert second.unit_cost == Decimal("76.52")
    # A soma do que foi rateado é exatamente a taxa informada.
    assert first.extras_amount + second.extras_amount == Decimal("9.31")
