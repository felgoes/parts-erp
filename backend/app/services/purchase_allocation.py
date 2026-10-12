"""Rateio determinístico dos valores de compra (P0).

O preview da revisão da importação (frontend) e a gravação (backend) usam exatamente este
algoritmo: custo base por unidade, rateio de frete, impostos e desconto proporcional ao
subtotal da linha, com a sobra de centavos no item de maior valor. Tudo é calculado em
inteiros (centavos e milésimos de unidade) para que as duas linguagens cheguem ao mesmo
centavo, sem depender do arredondamento de ponto flutuante.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MILLI = 1000
CENTS = 100


class ImportPlanError(ValueError):
    """Proposta impossível: a revisão precisa ser corrigida antes de confirmar."""


def to_milli(value: Decimal | int | str | None) -> int:
    """Converte quantidade (até três casas) em milésimos de unidade."""
    return int((Decimal(value or 0) * MILLI).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_cents(value: Decimal | int | str | None) -> int:
    """Converte valor monetário (até duas casas) em centavos."""
    return int((Decimal(value or 0) * CENTS).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / CENTS).quantize(Decimal("0.01"))


def half_up_div(numerator: int, denominator: int) -> int:
    """Divisão inteira com arredondamento half-up (metade para cima, em módulo)."""
    if denominator == 0:
        raise ValueError("Divisão por zero no rateio de valores.")
    negative = (numerator < 0) != (denominator < 0)
    numerator, denominator = abs(numerator), abs(denominator)
    rounded = (2 * numerator + denominator) // (2 * denominator)
    return -rounded if negative else rounded


def split_cents(amount_cents: int, weights: Sequence[tuple[str, int]]) -> dict[str, int]:
    """Rateia um valor em centavos por peso, fechando a sobra no maior item (o primeiro)."""
    total_weight = sum(weight for _, weight in weights)
    if total_weight <= 0:
        return {key: 0 for key, _ in weights}
    shares = {key: half_up_div(amount_cents * weight, total_weight) for key, weight in weights}
    residual = amount_cents - sum(shares.values())
    if residual:
        largest = max(weights, key=lambda entry: entry[1])[0]
        shares[largest] += residual
    return shares


def format_brl(cents: int) -> str:
    """Formata centavos como `R$ 1.234,56`, igual ao preview do frontend."""
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    integer, fraction = divmod(absolute, CENTS)
    grouped = f"{integer:,}".replace(",", ".")
    return f"{sign}R$ {grouped},{fraction:02d}"


@dataclass(frozen=True)
class ImportLinePlan:
    """Valores de uma linha depois do rateio do documento."""

    base_unit_cost: Decimal
    unit_cost: Decimal
    freight_amount: Decimal
    tax_amount: Decimal
    extras_amount: Decimal
    discount_amount: Decimal


@dataclass(frozen=True)
class ImportPlan:
    """Resultado do rateio do documento: é o que o preview mostra e o que fica gravado."""

    lines: list[ImportLinePlan]
    items_subtotal: Decimal
    freight_amount: Decimal
    tax_amount: Decimal
    extras_amount: Decimal
    discount_amount: Decimal
    computed_total: Decimal
    document_total: Decimal | None
    total: Decimal
    difference: Decimal

    @property
    def item_costs(self) -> list[Decimal]:
        return [line.base_unit_cost for line in self.lines]


def build_import_plan(
    lines: Sequence[tuple[Decimal, Decimal, Decimal]],
    *,
    freight_amount: Decimal | int | str = 0,
    tax_amount: Decimal | int | str = 0,
    extras_amount: Decimal | int | str = 0,
    discount_amount: Decimal | int | str = 0,
    document_total: Decimal | int | str | None = None,
) -> ImportPlan:
    """Rateia o documento importado.

    `lines` traz `(quantidade, custo unitário do papel, desconto da linha)`. O desconto da
    linha vira custo unitário líquido da própria linha; frete, impostos e desconto do
    documento são rateados proporcionalmente ao subtotal de cada linha.
    """
    if not lines:
        raise ImportPlanError("Adicione pelo menos uma peça antes de confirmar a importação.")

    base_cents: list[int] = []
    quantity_milli: list[int] = []
    for quantity, unit_cost, line_discount in lines:
        milli = to_milli(quantity)
        if milli <= 0:
            raise ImportPlanError("Informe uma quantidade maior que zero em todas as peças.")
        cost = to_cents(unit_cost)
        discount = to_cents(line_discount)
        line_net = milli * cost - MILLI * discount
        if line_net < 0:
            raise ImportPlanError(
                "O desconto da linha é maior que o total desta peça. Revise o desconto."
            )
        quantity_milli.append(milli)
        base_cents.append(half_up_div(line_net, milli))

    weights = [
        (str(index), base_cents[index] * quantity_milli[index]) for index in range(len(lines))
    ]
    freight_cents = to_cents(freight_amount)
    tax_cents = to_cents(tax_amount)
    extras_cents = to_cents(extras_amount)
    discount_cents = to_cents(discount_amount)
    freight_share = split_cents(freight_cents, weights)
    tax_share = split_cents(tax_cents, weights)
    extras_share = split_cents(extras_cents, weights)
    discount_share = split_cents(discount_cents, weights)

    document_cents = None if document_total is None else to_cents(document_total)
    adjustments_cents = freight_cents + tax_cents + extras_cents - discount_cents
    if document_cents is not None and adjustments_cents > document_cents:
        raise ImportPlanError(
            "O frete, os impostos e as taxas extras menos o desconto superam o total do "
            "documento. "
            "Revise os valores."
        )

    item_plans: list[ImportLinePlan] = []
    for index in range(len(lines)):
        extra_cents = (
            freight_share[str(index)]
            + tax_share[str(index)]
            + extras_share[str(index)]
            - discount_share[str(index)]
        )
        landed_cents = base_cents[index] + half_up_div(extra_cents * MILLI, quantity_milli[index])
        if landed_cents < 0:
            raise ImportPlanError(
                "Os descontos deixam o custo de alguma peça negativo. Revise frete, "
                "impostos, taxas extras e desconto."
            )
        item_plans.append(
            ImportLinePlan(
                base_unit_cost=from_cents(base_cents[index]),
                unit_cost=from_cents(landed_cents),
                freight_amount=from_cents(freight_share[str(index)]),
                tax_amount=from_cents(tax_share[str(index)]),
                extras_amount=from_cents(extras_share[str(index)]),
                discount_amount=from_cents(discount_share[str(index)]),
            )
        )

    subtotal_cents = half_up_div(
        sum(base_cents[index] * quantity_milli[index] for index in range(len(lines))), MILLI
    )
    computed_cents = subtotal_cents + adjustments_cents
    if computed_cents < 0:
        raise ImportPlanError(
            "O total é menor que o frete e os impostos menos o desconto. Revise os valores."
        )
    if document_cents is not None:
        difference_cents = computed_cents - document_cents
        if abs(difference_cents) > len(lines):
            raise ImportPlanError(
                "A soma dos itens não fecha com o total do documento: a diferença é de "
                f"{format_brl(abs(difference_cents))}. Confira itens, frete, impostos e desconto."
            )
        total_cents = document_cents
    else:
        difference_cents = 0
        total_cents = computed_cents

    return ImportPlan(
        lines=item_plans,
        items_subtotal=from_cents(subtotal_cents),
        freight_amount=from_cents(freight_cents),
        tax_amount=from_cents(tax_cents),
        extras_amount=from_cents(extras_cents),
        discount_amount=from_cents(discount_cents),
        computed_total=from_cents(computed_cents),
        document_total=None if document_cents is None else from_cents(document_cents),
        total=from_cents(total_cents),
        difference=from_cents(difference_cents),
    )
