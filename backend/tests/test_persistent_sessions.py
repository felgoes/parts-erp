from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.routes.auth import login, logout
from app.api.routes.users import reset_password
from app.core.security import decode_token, hash_password
from app.models import AuthSession, User, UserRole
from app.schemas.common import UserPasswordUpdate


def _user(db) -> User:
    user = User(
        email="session@example.com",
        full_name="Sessão QA",
        password_hash=hash_password("uma-senha-segura"),
        role=UserRole.admin,
        active=True,
    )
    db.add(user)
    db.commit()
    return user


def _login(db, user: User, remember_me: bool):
    return login(
        SimpleNamespace(username=user.email, password="uma-senha-segura"),
        db,
        remember_me,
    )


def test_stay_signed_in_creates_non_expiring_revocable_session(db) -> None:
    user = _user(db)
    session = _login(db, user, remember_me=True)
    payload = decode_token(session.access_token)

    assert session.persistent is True
    assert "exp" not in payload
    assert db.get(AuthSession, payload["sid"]) is not None
    assert get_current_user(session.access_token, db).id == user.id

    logout(session.access_token, db, user)

    assert db.get(AuthSession, payload["sid"]) is None
    with pytest.raises(HTTPException) as error:
        get_current_user(session.access_token, db)
    assert error.value.status_code == 401


def test_default_login_keeps_existing_expiring_session_behavior(db) -> None:
    user = _user(db)
    session = _login(db, user, remember_me=False)
    payload = decode_token(session.access_token)

    assert session.persistent is False
    assert "exp" in payload
    assert "sid" not in payload
    assert list(db.scalars(select(AuthSession))) == []


def test_password_reset_revokes_persistent_sessions(db) -> None:
    user = _user(db)
    session = _login(db, user, remember_me=True)
    reset_password(
        user.id,
        UserPasswordUpdate(password="outra-senha-segura"),
        db,
        user,
    )

    with pytest.raises(HTTPException) as error:
        get_current_user(session.access_token, db)
    assert error.value.status_code == 401


def test_login_form_and_api_support_manual_persistent_session(db) -> None:
    from app.db.session import get_db
    from app.main import app

    user = _user(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                data={
                    "username": user.email,
                    "password": "uma-senha-segura",
                    "remember_me": "true",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["persistent"] is True
            headers = {"Authorization": f"Bearer {payload['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
