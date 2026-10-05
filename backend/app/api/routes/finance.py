from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import InvoiceStatus, MovementType, Product, SalesInvoice, StockMovement, User
from app.schemas.common import FinanceDailyMetric, FinanceOverview, FinanceProductMetric

router = APIRouter(prefix="/finance", tags=["Financeiro e custos"])
BRAZIL_TZ = timezone(timedelta(hours=-3))
ZERO = Decimal("0")


def _period(
    start_date: date | None, end_date: date | None
) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(BRAZIL_TZ).date()
    start = start_date or today.replace(day=1)
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if (end - start).days > 364:
        raise HTTPException(status_code=422, detail="O período máximo é de 365 dias")
    since = datetime.combine(start, time.min, BRAZIL_TZ).astimezone(UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, BRAZIL_TZ).astimezone(UTC)
    return start, end, since, until


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@router.get("/overview", response_model=FinanceOverview)
def overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FinanceOverview:
    start, end, since, until = _period(start_date, end_date)
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.created_at >= since, StockMovement.created_at < until)
            .order_by(StockMovement.created_at)
        )
    )
    products = list(db.scalars(select(Product).order_by(Product.name)))
    invoices = list(
        db.scalars(
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.items))
            .where(
                SalesInvoice.status == InvoiceStatus.confirmed,
                func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at) >= since,
                func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at) < until,
            )
        )
    )

    totals = defaultdict(lambda: ZERO)
    product_totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    day_totals: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    known_movements = 0
    unknown_cost_movements = 0
    for movement in movements:
        quantity = Decimal(movement.quantity)
        amount = Decimal(movement.movement_value) if movement.movement_value is not None else None
        movement_day = _as_utc(movement.created_at).astimezone(BRAZIL_TZ).date()
        row = product_totals[movement.product_id]
        day = day_totals[movement_day]
        if amount is None:
            unknown_cost_movements += 1
        else:
            known_movements += 1
        if quantity > 0:
            totals["inbound_quantity"] += quantity
            row["inbound_quantity"] += quantity
            if amount is not None:
                totals["inbound_value"] += amount
                row["inbound_value"] += amount
                day["inbound_value"] += amount
        elif quantity < 0:
            totals["outbound_quantity"] += abs(quantity)
            row["outbound_quantity"] += abs(quantity)
            if amount is not None:
                totals["outbound_value"] += amount
                row["outbound_value"] += amount
                day["outbound_value"] += amount
        if movement.movement_type == MovementType.cancellation:
            totals["return_quantity"] += abs(quantity)
            row["return_quantity"] += abs(quantity)
            if amount is not None:
                totals["return_value"] += amount
                row["return_value"] += amount
                day["return_value"] += amount

    revenue = ZERO
    sale_item_keys: dict[str, tuple[str, Decimal]] = {}
    for invoice in invoices:
        revenue += Decimal(invoice.total)
        issued = _as_utc(invoice.issued_at or invoice.created_at).astimezone(BRAZIL_TZ).date()
        day_totals[issued]["revenue"] += Decimal(invoice.total)
        for item in invoice.items:
            sale_item_keys[f"invoice:{invoice.id}:item:{item.id}:confirm"] = (
                item.product_id,
                Decimal(item.quantity),
            )

    sale_movements = (
        list(
            db.scalars(
                select(StockMovement).where(
                    StockMovement.idempotency_key.in_(sale_item_keys)
                )
            )
        )
        if sale_item_keys
        else []
    )
    sale_by_key = {movement.idempotency_key: movement for movement in sale_movements}
    unvalued_sales_items = 0
    for key, (product_id, quantity) in sale_item_keys.items():
        movement = sale_by_key.get(key)
        if (
            movement is None
            or movement.movement_value is None
            or abs(Decimal(movement.quantity)) != quantity
        ):
            unvalued_sales_items += 1
            continue
        amount = Decimal(movement.movement_value)
        totals["net_cost_of_goods"] += amount
        product_totals[product_id]["net_cost_of_goods"] += amount

    # A return against an invoice that remains confirmed reduces COGS on its return date.
    confirmed_ids = {invoice.id for invoice in invoices}
    for movement in movements:
        if (
            movement.movement_type == MovementType.cancellation
            and movement.reference in confirmed_ids
        ):
            if movement.movement_value is None:
                unvalued_sales_items += 1
            else:
                amount = Decimal(movement.movement_value)
                totals["net_cost_of_goods"] -= amount
                product_totals[movement.product_id]["net_cost_of_goods"] -= amount

    inventory_units = sum((Decimal(product.current_stock) for product in products), ZERO)
    inventory_value = sum(
        (Decimal(product.current_stock) * Decimal(product.cost_price) for product in products), ZERO
    )
    gross_margin = (
        revenue - totals["net_cost_of_goods"] if unvalued_sales_items == 0 else None
    )
    gross_margin_percent = (
        gross_margin / revenue * Decimal("100")
        if gross_margin is not None and revenue
        else (ZERO if gross_margin is not None else None)
    )
    by_product = []
    for product in products:
        row = product_totals[product.id]
        if product.current_stock or any(row.values()):
            by_product.append(
                FinanceProductMetric(
                    product_id=product.id,
                    sku=product.sku,
                    name=product.name,
                    current_stock=Decimal(product.current_stock),
                    average_cost=Decimal(product.cost_price),
                    inventory_value=Decimal(product.current_stock) * Decimal(product.cost_price),
                    inbound_quantity=row["inbound_quantity"],
                    inbound_value=row["inbound_value"],
                    outbound_quantity=row["outbound_quantity"],
                    outbound_value=row["outbound_value"],
                    return_quantity=row["return_quantity"],
                    return_value=row["return_value"],
                    net_cost_of_goods=row["net_cost_of_goods"],
                )
            )
    by_product.sort(key=lambda item: item.inventory_value, reverse=True)
    daily = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        values = day_totals[day]
        daily.append(
            FinanceDailyMetric(
                date=day,
                label=day.strftime("%d/%m"),
                inbound_value=values["inbound_value"],
                outbound_value=values["outbound_value"],
                return_value=values["return_value"],
                revenue=values["revenue"],
            )
        )
    return FinanceOverview(
        period_label=f"{start:%d/%m/%Y} a {end:%d/%m/%Y}",
        inventory_units=inventory_units,
        inventory_value=inventory_value,
        inbound_quantity=totals["inbound_quantity"],
        inbound_value=totals["inbound_value"],
        outbound_quantity=totals["outbound_quantity"],
        outbound_value=totals["outbound_value"],
        return_quantity=totals["return_quantity"],
        return_value=totals["return_value"],
        net_cost_of_goods=totals["net_cost_of_goods"],
        revenue=revenue,
        gross_margin=gross_margin,
        gross_margin_percent=gross_margin_percent,
        known_movements=known_movements,
        unknown_cost_movements=unknown_cost_movements,
        unvalued_sales_items=unvalued_sales_items,
        by_product=by_product,
        daily=daily,
    )
