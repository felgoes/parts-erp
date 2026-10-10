"""Shared rules for accounts payable titles and their payments."""

from decimal import Decimal

from app.models import PurchasePayable


def payment_total(payable: PurchasePayable) -> Decimal:
    return sum(
        (Decimal(payment.amount) for payment in payable.payments), Decimal("0")
    ).quantize(Decimal("0.01"))


def payable_balance(payable: PurchasePayable) -> Decimal:
    return (Decimal(payable.amount) - payment_total(payable)).quantize(Decimal("0.01"))


def refresh_payable(payable: PurchasePayable) -> None:
    """Payments are the source of truth: recompute the settled amount and the title status."""
    paid = payment_total(payable)
    payable.paid_amount = paid
    if payable.status == "cancelled":
        return
    if paid <= 0:
        payable.status = "open"
    elif paid < Decimal(payable.amount):
        payable.status = "partial"
    else:
        payable.status = "paid"
