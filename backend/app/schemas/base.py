"""Bases dos esquemas de resposta.

Separado de `common.py` para os módulos de esquema novos poderem usá-las sem depender do
arquivo principal (e para o arquivo principal não crescer).
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class UtcModel(BaseModel):
    @field_serializer("*", when_used="json")
    def serialize_utc_datetimes(self, value: Any) -> Any:
        """SQLite stores our UTC timestamps without tzinfo; make that explicit in JSON."""
        if isinstance(value, datetime):
            normalized = (
                value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            )
            return normalized.isoformat().replace("+00:00", "Z")
        return value


class ORMModel(UtcModel):
    model_config = ConfigDict(from_attributes=True)
