"""Orçamento mensal compartilhado e contabilização persistente das chamadas."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.catalog import price_for
from app.models.assistant import AssistantConfiguration, AssistantUsage

try:
    ERP_TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # Termux pode não ter o pacote tzdata.
    ERP_TZ = timezone(timedelta(hours=-3))
CENT = Decimal("0.000001")
ALERT_PERCENT = Decimal("80")


class AssistantBudgetError(Exception):
    def __init__(self, message: str, *, used: Decimal = Decimal("0")) -> None:
        super().__init__(message)
        self.message = message
        self.used = used


def month_window(moment: datetime | None = None) -> tuple[datetime, datetime]:
    local = (moment or datetime.now(UTC)).astimezone(ERP_TZ)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start.astimezone(UTC), end.astimezone(UTC)


def usage_total(db: Session, moment: datetime | None = None) -> Decimal:
    start, end = month_window(moment)
    rows = db.execute(
        select(AssistantUsage.reserved_cost_usd, AssistantUsage.estimated_cost_usd).where(
            AssistantUsage.created_at >= start,
            AssistantUsage.created_at < end,
            AssistantUsage.status != "failed",
        )
    )
    total = Decimal("0")
    for reserved, estimated in rows:
        total += max(Decimal(reserved or 0), Decimal(estimated or 0))
    return total.quantize(CENT, rounding=ROUND_HALF_UP)


def state(db: Session, config: AssistantConfiguration | None) -> dict:
    used = usage_total(db)
    limit = Decimal(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    percent = (
        (used / limit * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if limit
        else None
    )
    _, resets_at = month_window()
    return {
        "monthly_limit_usd": str(limit) if limit is not None else None,
        "used_usd": str(used),
        "percent_used": str(percent) if percent is not None else None,
        "alert": bool(percent is not None and percent >= ALERT_PERCENT),
        "blocked": bool(limit is not None and used >= limit),
        "resets_at": resets_at.isoformat().replace("+00:00", "Z"),
        "currency": "USD",
        "pricing_updated_at": None,
    }


def reserve(
    db: Session,
    *,
    config: AssistantConfiguration,
    user_id: str,
    conversation_id: str | None,
    request_id: str,
    estimated_input_tokens: int,
    max_output_tokens: int,
) -> AssistantUsage:
    """Reserva o pior custo plausível antes da chamada, serializando a checagem no banco."""
    model = price_for(config.provider, config.model)
    if model is None:
        raise AssistantBudgetError(
            "O modelo configurado não tem preço de referência; o assistente fica bloqueado "
            "até o administrador escolher um modelo suportado"
        )
    limit_row = db.scalar(
        select(AssistantConfiguration)
        .where(AssistantConfiguration.id == config.id)
        .with_for_update()
    )
    limit = Decimal(limit_row.monthly_budget_usd or 0) if limit_row else Decimal("0")
    if limit <= 0:
        raise AssistantBudgetError(
            "Defina o limite mensal do assistente em Integrações antes de usar o chat"
        )
    used = usage_total(db)
    reserved_cost = (
        Decimal(estimated_input_tokens) / Decimal(1_000_000) * model.input_per_million
        + Decimal(max_output_tokens) / Decimal(1_000_000) * model.output_per_million
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    if used + reserved_cost > limit:
        raise AssistantBudgetError(
            "O limite mensal estimado do assistente foi atingido; o uso volta no próximo "
            "início de mês ou após o administrador aumentar o limite",
            used=used,
        )
    row = AssistantUsage(
        request_id=request_id,
        conversation_id=conversation_id,
        user_id=user_id,
        provider=config.provider,
        model=config.model,
        status="reserved",
        reserved_cost_usd=reserved_cost,
        estimated_cost_usd=0,
    )
    db.add(row)
    db.commit()
    return row


def settle(db: Session, usage: AssistantUsage, input_tokens: int, output_tokens: int) -> None:
    model = price_for(usage.provider, usage.model)
    if model is None:
        usage.status, usage.estimated_cost_usd = "unpriced", Decimal("0")
    else:
        usage.estimated_cost_usd = (
            Decimal(input_tokens) / Decimal(1_000_000) * model.input_per_million
            + Decimal(output_tokens) / Decimal(1_000_000) * model.output_per_million
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        usage.status = "completed"
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.completed_at = datetime.now(UTC)
    db.commit()


def release(db: Session, usage: AssistantUsage) -> None:
    usage.status = "failed"
    usage.estimated_cost_usd = Decimal("0")
    usage.completed_at = datetime.now(UTC)
    db.commit()
