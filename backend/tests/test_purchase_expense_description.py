"""Despesa da empresa: o gasto tem título próprio, não só a categoria.

A categoria ("Serviços", "Impostos e taxas") é um balde; o título é o que o operador escreve
("Certificado digital A1", "Imposto do mês") e o que aparece na lista, no detalhe e no título a
pagar, permitindo identificar a despesa depois de lançada.
"""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.api.routes.payables import list_payables
from app.api.routes.purchases import create_purchase, get_purchase, update_purchase
from app.api.routes.purchases_list import list_purchases
from app.schemas.common import PurchaseCreate, PurchaseUpdate


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id="user-finance", full_name="Financeiro QA")


def _expense(
    db: Session,
    user: SimpleNamespace,
    *,
    description: str | None = "Certificado digital A1",
    category: str = "Serviços",
) -> str:
    expense = create_purchase(
        PurchaseCreate(
            purchase_type="expense",
            expense_category=category,
            expense_amount=Decimal("249.90"),
            expense_description=description,
            supplier_name="Certificadora Exemplo",
            document_date=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        db,
        user,
    )
    return expense.id


def test_description_travels_from_form_to_detail_list_and_payable(db: Session) -> None:
    user = _actor()
    purchase_id = _expense(db, user)

    detail = get_purchase(purchase_id, db=db, user=user)
    assert detail.expense_description == "Certificado digital A1"

    page = list_purchases(limit=25, offset=0, db=db, user=user)
    row = next(item for item in page.items if item.id == purchase_id)
    assert row.expense_description == "Certificado digital A1"

    payables = list_payables(
        status=None,
        supplier=None,
        search=None,
        due_from=None,
        due_to=None,
        paid_from=None,
        paid_to=None,
        overdue_only=False,
        next_days=7,
        limit=200,
        offset=0,
        db=db,
        _=user,
    )
    payable = next(item for item in payables.items if item.purchase_id == purchase_id)
    assert payable.expense_description == "Certificado digital A1"
    assert payable.expense_category == "Serviços"


def test_description_is_optional_and_can_be_edited_later(db: Session) -> None:
    user = _actor()
    purchase_id = _expense(db, user, description=None, category="Impostos e taxas")

    # Despesa antiga ou lançada por importação continua válida sem título.
    assert get_purchase(purchase_id, db=db, user=user).expense_description is None

    updated = update_purchase(
        purchase_id, PurchaseUpdate(expense_description="Imposto do mês"), db, user
    )
    assert updated.expense_description == "Imposto do mês"
    assert get_purchase(purchase_id, db=db, user=user).expense_description == "Imposto do mês"
