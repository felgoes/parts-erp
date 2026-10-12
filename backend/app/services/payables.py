"""Regras compartilhadas de contas a pagar: título, condição de pagamento e parcelas."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from app.models import PayableInstallment, PurchasePayable

PAYMENT_TYPES = ("cash", "installments", "entry")
MAX_INSTALLMENTS = 36
MAX_DAYS = 3650


def payment_total(payable: PurchasePayable) -> Decimal:
    return sum((Decimal(payment.amount) for payment in payable.payments), Decimal("0")).quantize(
        Decimal("0.01")
    )


def payable_balance(payable: PurchasePayable) -> Decimal:
    return (Decimal(payable.amount) - payment_total(payable)).quantize(Decimal("0.01"))


def installment_paid_total(installment: PayableInstallment) -> Decimal:
    return sum(
        (Decimal(payment.amount) for payment in installment.payments), Decimal("0")
    ).quantize(Decimal("0.01"))


def installment_balance(installment: PayableInstallment) -> Decimal:
    return (Decimal(installment.amount) - installment_paid_total(installment)).quantize(
        Decimal("0.01")
    )


def refresh_payable(payable: PurchasePayable) -> None:
    """Payments are the source of truth: recompute the settled amount and the title status."""
    paid = payment_total(payable)
    payable.paid_amount = paid
    for installment in payable.installments:
        installment.paid_amount = installment_paid_total(installment)
    if payable.status == "cancelled":
        return
    if paid <= 0:
        payable.status = "open"
    elif paid < Decimal(payable.amount):
        payable.status = "partial"
    else:
        payable.status = "paid"


def normalize_condition(
    payment_type: str | None,
    installment_count: int | None,
    first_due_days: int | None,
    interval_days: int | None,
) -> tuple[str, int, int, int]:
    """Valida a condição de pagamento e devolve a versão normalizada (P12)."""
    kind = (payment_type or "cash").strip().lower()
    if kind not in PAYMENT_TYPES:
        raise ValueError("Condição de pagamento inválida.")
    first = int(first_due_days or 0)
    if first < 0 or first > MAX_DAYS:
        raise ValueError(f"O prazo do primeiro vencimento deve ficar entre 0 e {MAX_DAYS} dias.")
    if kind == "cash":
        return kind, 1, first, 0
    count = int(installment_count or 1)
    if count < 1 or count > MAX_INSTALLMENTS:
        raise ValueError(f"O número de parcelas deve ficar entre 1 e {MAX_INSTALLMENTS}.")
    interval = int(interval_days or 0)
    if interval < 1 or interval > MAX_DAYS:
        raise ValueError(f"O intervalo entre parcelas deve ficar entre 1 e {MAX_DAYS} dias.")
    return kind, count, first, interval


def schedule_offsets(kind: str, count: int, first_due_days: int, interval_days: int) -> list[int]:
    """Dias de vencimento de cada parcela, contados a partir da data base."""
    if kind == "cash":
        return [first_due_days]
    if kind == "entry":
        return [first_due_days] + [
            first_due_days + (index + 1) * interval_days for index in range(count)
        ]
    return [first_due_days + index * interval_days for index in range(count)]


def condition_label(kind: str, count: int, first_due_days: int, interval_days: int) -> str:
    """Condição legível guardada no título, do jeito que o fornecedor combinou."""
    if kind == "cash":
        return "À vista" if first_due_days == 0 else f"À vista em {first_due_days} dias"
    offsets = schedule_offsets(kind, count, first_due_days, interval_days)
    if kind == "entry":
        return "Entrada + " + "/".join(str(offset) for offset in offsets[1:])
    return "/".join(str(offset) for offset in offsets)


def split_amounts(total: Decimal, parts: int) -> list[Decimal]:
    """Divide o valor em parcelas iguais; a sobra de centavos fica na última."""
    if parts <= 0:
        raise ValueError("Informe pelo menos uma parcela.")
    total = Decimal(total).quantize(Decimal("0.01"))
    base = (total / parts).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    amounts = [base] * (parts - 1)
    amounts.append((total - base * (parts - 1)).quantize(Decimal("0.01")))
    return amounts


def apply_payment_condition(
    payable: PurchasePayable,
    *,
    base_date: datetime,
    condition: tuple[str, int, int, int] | None = None,
) -> None:
    """(Re)gera as parcelas do título conforme a condição, preservando as já baixadas."""
    kind, count, first, interval = condition or normalize_condition(
        payable.payment_type,
        payable.installment_count,
        payable.first_due_days,
        payable.interval_days,
    )
    payable.payment_type = kind
    payable.installment_count = count
    payable.first_due_days = first
    payable.interval_days = interval
    payable.payment_terms = condition_label(kind, count, first, interval)

    kept = sorted(
        (item for item in payable.installments if Decimal(item.paid_amount or 0) > 0),
        key=lambda item: item.number,
    )
    for installment in list(payable.installments):
        if installment not in kept:
            payable.installments.remove(installment)

    kept_total = sum((Decimal(item.amount) for item in kept), Decimal("0"))
    remaining = (Decimal(payable.amount) - kept_total).quantize(Decimal("0.01"))
    if remaining > 0:
        offsets = schedule_offsets(kind, count, first, interval)
        amounts = split_amounts(remaining, len(offsets))
        if any(amount <= 0 for amount in amounts):
            raise ValueError(
                "O valor do título não permite essa quantidade de parcelas sem parcela zerada."
            )
        for position, (offset, amount) in enumerate(
            zip(offsets, amounts, strict=True), start=len(kept) + 1
        ):
            payable.installments.append(
                PayableInstallment(
                    number=position,
                    due_date=base_date + timedelta(days=offset),
                    amount=amount,
                )
            )
    if payable.installments:
        # Datas vindas do SQLite podem estar sem fuso; compare sempre em UTC.
        payable.due_date = min(
            item.due_date if item.due_date.tzinfo else item.due_date.replace(tzinfo=UTC)
            for item in payable.installments
        )
