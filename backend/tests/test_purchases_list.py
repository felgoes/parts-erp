"""Lista de compras (P1): projeção leve, busca no servidor, período/etapa e paginação."""

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.periods import BRAZIL_TZ
from app.api.routes.purchases import create_purchase, get_purchase
from app.api.routes.purchases_list import list_purchases
from app.schemas.common import PurchaseCreate, PurchaseItemCreate


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id="user-qa", full_name="QA")


def _purchase(db: Session, *, supplier: str, sku: str, description: str = "Peça de amostra") -> str:
    purchase = create_purchase(
        PurchaseCreate(
            supplier_name=supplier,
            items=[PurchaseItemCreate(sku=sku, description=description, quantity=1)],
        ),
        db,
        _actor(),
    )
    return purchase.number


def test_list_is_a_light_page_with_summary_and_total(db: Session) -> None:
    number = _purchase(db, supplier="Fornecedor Lista", sku="L-1")
    page = list_purchases(limit=25, offset=0, db=db, user=_actor())

    assert page.total == 1
    assert [row.number for row in page.items] == [number]
    row = page.items[0].items[0]
    assert row.sku == "L-1"
    assert "unit_cost" not in row.model_dump(), "a linha da lista não carrega custo"
    assert "freight_amount" not in row.model_dump()
    assert page.summary.negotiating == 1
    assert page.summary.ordered == 0
    assert page.summary.received == 0

    detail = get_purchase(page.items[0].id, db=db, user=_actor())
    assert detail.events, "o detalhe continua trazendo o histórico"
    assert detail.items[0].unit_cost is not None, "o detalhe continua trazendo o custo"


def test_search_matches_number_supplier_sku_and_description(db: Session) -> None:
    number = _purchase(
        db, supplier="Distribuidora Alfa", sku="ABC-123", description="Correia dentada"
    )
    _purchase(db, supplier="Outro Fornecedor", sku="ZZZ-999", description="Vela de ignição")

    for term in ("alfa", "ABC-123", "correia", number):
        page = list_purchases(limit=25, offset=0, search=term, db=db, user=_actor())
        assert [row.number for row in page.items] == [number], term


def test_status_and_period_filter_on_the_server(db: Session) -> None:
    _purchase(db, supplier="Recente", sku="R-1")

    page = list_purchases(limit=25, offset=0, status="negotiating", db=db, user=_actor())
    assert page.total == 1
    page = list_purchases(limit=25, offset=0, status="received", db=db, user=_actor())
    assert page.total == 0 and page.items == []

    # A janela do filtro é o dia de calendário da operação (America/Sao_Paulo), não o dia UTC:
    # entre 21h e meia-noite de São Paulo o dia UTC já virou e o teste falhava sozinho.
    today = datetime.now(BRAZIL_TZ).date()
    page = list_purchases(
        limit=25, offset=0, start_date=today, end_date=today, db=db, user=_actor()
    )
    assert page.total == 1
    long_ago = datetime(2020, 1, 1, tzinfo=UTC).date()
    page = list_purchases(
        limit=25, offset=0, start_date=long_ago, end_date=long_ago, db=db, user=_actor()
    )
    assert page.total == 0


def test_pagination_does_not_overlap_and_summary_counts_the_period(db: Session) -> None:
    for index in range(3):
        _purchase(db, supplier=f"Fornecedor {index}", sku=f"P-{index}")

    first = list_purchases(limit=2, offset=0, db=db, user=_actor())
    second = list_purchases(limit=2, offset=2, db=db, user=_actor())

    assert first.total == second.total == 3
    assert len(first.items) == 2 and len(second.items) == 1
    assert not ({row.id for row in first.items} & {row.id for row in second.items})
    assert first.summary.negotiating == 3
