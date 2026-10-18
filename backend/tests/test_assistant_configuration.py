import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import get_current_user
from app.core.security import decrypt_secret
from app.db.session import get_db
from app.main import app
from app.models import User, UserRole
from app.models.assistant import AssistantConfiguration


def test_shared_configuration_protects_key_and_restricts_access(db):
    first = User(
        email="first-config@example.test",
        full_name="Primeiro",
        password_hash="x",
        role=UserRole.admin,
    )
    second = User(
        email="second-config@example.test",
        full_name="Segundo",
        password_hash="x",
        role=UserRole.admin,
    )
    operator = User(
        email="operator-config@example.test",
        full_name="Operador",
        password_hash="x",
        role=UserRole.operator,
    )
    db.add_all([first, second, operator])
    db.commit()
    current = [first]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current[0]
    dummy_key = "example credential never sent to a real service"
    try:
        with TestClient(app) as client:
            path = "/api/v1/assistant/configuration"
            saved = client.put(
                path,
                json={
                    "provider": "openai",
                    "model": "example-model",
                    "key_action": "replace",
                    "api_key": dummy_key,
                },
            )
            assert saved.status_code == 200
            assert saved.json() == {
                "provider": "openai",
                "model": "example-model",
                "has_api_key": True,
            }
            assert dummy_key not in saved.text
            assert saved.headers["cache-control"] == "no-store"
            config = db.scalar(select(AssistantConfiguration))
            assert config.encrypted_api_key != dummy_key
            assert decrypt_secret(config.encrypted_api_key) == dummy_key

            current[0] = second
            shared = client.get(path)
            assert shared.json() == saved.json()
            assert shared.headers["cache-control"] == "no-store"
            assert dummy_key not in shared.text
            denied_change = client.put(
                path, json={"provider": "gemini", "model": "example-model", "key_action": "keep"}
            )
            assert denied_change.status_code == 409
            assert client.get(path).json()["provider"] == "openai"
            switched = client.put(
                path, json={"provider": "gemini", "model": "example-model", "key_action": "remove"}
            )
            assert switched.json() == {
                "provider": "gemini",
                "model": "example-model",
                "has_api_key": False,
            }
            db.refresh(config)
            assert config.encrypted_api_key is None

            current[0] = operator
            assert client.get(path).status_code == 403
            assert (
                client.put(
                    path,
                    json={
                        "provider": "deepseek",
                        "model": "x",
                        "key_action": "replace",
                        "api_key": dummy_key,
                    },
                ).status_code
                == 403
            )
            current[0] = first
            assert client.get(path).json()["provider"] == "gemini"
    finally:
        app.dependency_overrides.clear()


def test_validation_never_reflects_sensitive_payload(db):
    admin = User(
        email="validation@example.test", full_name="Admin", password_hash="x", role=UserRole.admin
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin
    marker = "sensitive-input-not-for-output"
    try:
        with TestClient(app) as client:
            path = "/api/v1/assistant/configuration"
            cases = [
                {
                    "provider": "unknown",
                    "model": "example",
                    "key_action": "replace",
                    "api_key": marker,
                },
                {
                    "provider": "openai",
                    "model": marker + "?",
                    "key_action": "replace",
                    "api_key": marker,
                },
                {"provider": "openai", "model": "example", "key_action": "keep", "api_key": marker},
                {
                    "provider": "openai",
                    "model": "example",
                    "key_action": "replace",
                    "api_key": marker,
                    "extra": marker,
                },
            ]
            for payload in cases:
                response = client.put(path, json=payload)
                assert response.status_code == 400
                assert marker not in response.text
            too_large = client.put(path, content=marker * 500)
            assert too_large.status_code == 413
            assert marker not in too_large.text
            assert db.get(AssistantConfiguration, "shared") is None
    finally:
        app.dependency_overrides.clear()


def test_concurrent_updates_are_not_silently_overwritten(db):
    db.add(AssistantConfiguration(id="shared", provider="openai", model="first"))
    db.commit()
    with (
        Session(db.bind, expire_on_commit=False) as first,
        Session(db.bind, expire_on_commit=False) as second,
    ):
        first_config = first.get(AssistantConfiguration, "shared")
        second_config = second.get(AssistantConfiguration, "shared")
        first_config.provider = "gemini"
        first.commit()
        second_config.model = "second"
        with pytest.raises(StaleDataError):
            second.commit()
        second.rollback()
    db.expire_all()
    assert db.get(AssistantConfiguration, "shared").provider == "gemini"
    assert db.get(AssistantConfiguration, "shared").model == "first"


@pytest.mark.parametrize("provider", ["openai", "deepseek", "gemini", "anthropic"])
def test_supported_provider_names_are_configurable(db, provider):
    admin = User(
        email="providers@example.test", full_name="Admin", password_hash="x", role=UserRole.admin
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/assistant/configuration",
                json={"provider": provider, "model": "sample-model", "key_action": "remove"},
            )
            assert response.status_code == 200
            assert response.json()["provider"] == provider
            assert response.json()["has_api_key"] is False
    finally:
        app.dependency_overrides.clear()
