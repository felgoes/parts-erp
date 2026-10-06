import base64

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.routes.settings import read_settings, update_settings
from app.core.permissions import Permission, has_permission
from app.models import ErpSettings, User, UserRole
from app.schemas.common import ErpSettingsUpdate


def _png_data_url() -> str:
    image = Image.new("RGB", (2, 2), color="green")
    import io

    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def test_first_settings_read_returns_defaults_without_writing(db) -> None:
    user = User(id="user-settings", email="read@example.com", role=UserRole.admin)

    result = read_settings(db, user)

    assert result.company_name == "Parts ERP"
    assert result.company_short_name == "Parts"
    assert result.backup_ready is False
    assert db.query(ErpSettings).count() == 0


def test_company_brand_and_backup_policy_are_persisted(db) -> None:
    admin = User(id="admin-settings", email="settings@example.com", role=UserRole.admin)
    payload = ErpSettingsUpdate(
        company_name="Goes Auto Parts",
        company_short_name="Goes",
        logo_data_url=_png_data_url(),
        backup_enabled=True,
        backup_frequency="weekly",
        backup_retention_days=30,
        backup_destination="google_drive",
    )

    result = update_settings(payload, db, admin)

    assert result.company_name == "Goes Auto Parts"
    assert result.logo_data_url.startswith("data:image/png;base64,")
    assert result.backup_enabled is True
    assert result.backup_frequency == "weekly"
    assert result.backup_retention_days == 30
    assert result.backup_ready is False
    assert db.query(ErpSettings).count() == 1
    assert read_settings(db, admin).company_short_name == "Goes"


def test_logo_must_be_a_real_supported_image(db) -> None:
    admin = User(id="admin-settings", email="settings@example.com", role=UserRole.admin)
    payload = ErpSettingsUpdate(
        company_name="Goes Auto Parts",
        company_short_name="Goes",
        logo_data_url="data:image/png;base64,ZmFrZQ==",
    )

    with pytest.raises(HTTPException) as raised:
        update_settings(payload, db, admin)

    assert raised.value.status_code == 422
    assert db.query(ErpSettings).count() == 0


def test_backup_retention_never_exceeds_one_month() -> None:
    with pytest.raises(ValueError):
        ErpSettingsUpdate(
            company_name="Goes Auto Parts",
            company_short_name="Goes",
            backup_retention_days=31,
        )


def test_settings_configuration_is_admin_only() -> None:
    assert has_permission(UserRole.admin, Permission.SETTINGS_MANAGE)
    assert not has_permission(UserRole.manager, Permission.SETTINGS_MANAGE)
