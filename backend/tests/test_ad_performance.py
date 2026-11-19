from datetime import date

from app.services.ad_performance import _metric_date


def test_daily_marketplace_date_keeps_api_calendar_bucket():
    assert _metric_date("2026-11-19T00:00:00Z") == date(2026, 11, 19)


def test_daily_marketplace_date_accepts_plain_iso_date():
    assert _metric_date("2026-11-19") == date(2026, 11, 19)


def test_daily_marketplace_date_rejects_invalid_value():
    assert _metric_date("not-a-date") is None
