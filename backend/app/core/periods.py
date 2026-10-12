"""Janela de período operacional (America/Sao_Paulo) usada pelos filtros das telas.

As telas filtram por data de calendário no fuso da operação; o banco guarda UTC. Este módulo
concentra a conversão para que financeiro, contas a pagar e compras não repitam a mesma conta
com regras diferentes.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

from fastapi import HTTPException

BRAZIL_TZ = timezone(timedelta(hours=-3))
MAX_PERIOD_DAYS = 365


def resolve_period(
    start_date: date | None, end_date: date | None
) -> tuple[date, date, datetime, datetime]:
    """Devolve (início, fim, desde UTC, até UTC) validando ordem e tamanho do período."""
    today = datetime.now(BRAZIL_TZ).date()
    start = start_date or today.replace(day=1)
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if (end - start).days > MAX_PERIOD_DAYS - 1:
        raise HTTPException(status_code=422, detail=f"O período máximo é de {MAX_PERIOD_DAYS} dias")
    since = datetime.combine(start, time.min, BRAZIL_TZ).astimezone(UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, BRAZIL_TZ).astimezone(UTC)
    return start, end, since, until


def optional_period_window(
    start_date: date | None, end_date: date | None
) -> tuple[datetime | None, datetime | None]:
    """Janela para listas: sem data informada, não filtra nada (a tela escolhe o padrão)."""
    if start_date is None and end_date is None:
        return None, None
    _, _, since, until = resolve_period(start_date, end_date)
    return since, until
