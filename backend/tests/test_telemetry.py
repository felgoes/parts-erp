from app.api.routes.telemetry import collect_event
from app.schemas.common import TelemetryEventCreate
from app.models import TelemetryEvent


def test_public_event_collection_whitelists_properties(db):
    result = collect_event(
        payload=TelemetryEventCreate(
            name= "product_view",
            anonymous_id= "visitor-1",
            properties= {"sku": "P-1", "email": "should-not-be-stored"},
        ),
        db=db,
    )
    assert result == {"status": "accepted"}
    event = db.query(TelemetryEvent).one()
    assert event.properties == {"sku": "P-1"}
    assert event.visitor_hash
