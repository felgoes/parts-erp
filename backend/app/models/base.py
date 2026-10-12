"""Peças comuns dos modelos: identificador, marca de tempo e hora corrente em UTC.

Separado de `entities.py` para os módulos de modelo novos poderem usar estas peças sem
depender do arquivo principal (e para o arquivo principal não crescer).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
