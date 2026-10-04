from datetime import UTC, date, datetime

from starlette.requests import Request

from app.api.routes.telemetry import collect_event, summary
from app.models import TelemetryEvent, User
from app.schemas.common import TelemetryEventCreate


def request_stub() -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
            "method": "POST",
            "path": "/",
            "query_string": b"",
        }
    )


def test_public_event_collection_whitelists_properties(db):
    result = collect_event(
        payload=TelemetryEventCreate(
            name="product_view",
            anonymous_id="visitor-1",
            properties={"sku": "P-1", "email": "should-not-be-stored"},
        ),
        request=request_stub(),
        db=db,
    )
    assert result == {"status": "accepted"}
    event = db.query(TelemetryEvent).one()
    assert event.properties == {"sku": "P-1"}
    assert event.visitor_hash


def test_summary_includes_daily_events_in_brasilia_timezone(db):
    db.add_all(
        [
            TelemetryEvent(
                name="landing_view",
                source="site",
                properties={},
                created_at=datetime(2026, 10, 3, 2, 30, tzinfo=UTC),
            ),
            TelemetryEvent(
                name="product_view",
                source="site",
                properties={"sku": "P-1"},
                created_at=datetime(2026, 10, 3, 15, 0, tzinfo=UTC),
            ),
        ]
    )
    db.commit()

    result = summary(start_date=date(2026, 10, 2), end_date=date(2026, 10, 3), db=db, _=User())

    assert len(result.daily_events) == 2
    assert result.daily_events[0].date == date(2026, 10, 2)
    assert {event.name: event.count for event in result.daily_events[0].events} == {
        "landing_view": 1
    }
    assert result.daily_events[1].date == date(2026, 10, 3)
    assert {event.name: event.count for event in result.daily_events[1].events} == {
        "product_view": 1
    }
