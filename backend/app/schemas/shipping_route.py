from datetime import datetime

from app.schemas.base import UtcModel


class ShippingCheckpointOut(UtcModel):
    locality: str
    recorded_at: datetime | None


class ShippingRouteOut(UtcModel):
    origin: str | None
    destination: str | None
    checkpoints: list[ShippingCheckpointOut]
