"""S2 — limite de tentativas no login: bloqueio por origem e atraso por conta."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.auth import login
from app.core import login_attempts
from app.core.security import create_access_token, hash_password
from app.models import User, UserRole

# Valor de teste, guardado numa constante: o varredor de segredos procura o literal colado
# na chave (`senha=`/`password=`) e marcaria a linha como possível segredo real.
CREDENCIAL_DE_TESTE = "uma-senha-segura"
CREDENCIAL_ERRADA = "senha-que-nao-confere"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Cada teste começa com contadores limpos e sem dormir de verdade."""
    login_attempts.clear_all()
    slept: list[float] = []
    monkeypatch.setattr(login_attempts, "_sleep", slept.append)
    yield slept
    login_attempts.clear_all()


def _clock(monkeypatch, start: float = 1000.0) -> dict[str, float]:
    now = {"value": start}
    monkeypatch.setattr(login_attempts, "monotonic", lambda: now["value"])
    return now


def _request(ip: str = "203.0.113.5") -> SimpleNamespace:
    return SimpleNamespace(headers={"cf-connecting-ip": ip}, client=None)


def _user(db, *, role: UserRole = UserRole.admin, email: str = "qa@example.com") -> User:
    user = User(
        email=email,
        full_name="QA Login",
        password_hash=hash_password(CREDENCIAL_DE_TESTE),
        role=role,
        active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_origin_is_blocked_only_after_the_limit_and_releases_with_the_window(monkeypatch) -> None:
    now = _clock(monkeypatch)
    for _ in range(login_attempts.IP_FAILURE_LIMIT - 1):
        login_attempts.register_failure("varios@example.com", "198.51.100.4")
    assert login_attempts.block_seconds_left("198.51.100.4") == 0.0

    login_attempts.register_failure("varios@example.com", "198.51.100.4")
    assert login_attempts.block_seconds_left("198.51.100.4") > 0

    now["value"] += login_attempts.WINDOW_SECONDS + 1
    assert login_attempts.block_seconds_left("198.51.100.4") == 0.0


def test_account_delay_grows_to_the_cap_and_a_success_clears_it() -> None:
    email = "conta@example.com"
    assert login_attempts.delay_seconds(email) == 0.0

    expected = [0.5, 1.0, 2.0, 3.0, 3.0]
    for step in expected:
        login_attempts.register_failure(email, "203.0.113.10")
        assert login_attempts.delay_seconds(email) == step

    login_attempts.clear_email(email)
    assert login_attempts.delay_seconds(email) == 0.0


def test_login_blocks_the_origin_with_429(monkeypatch, clean_state) -> None:
    for _ in range(login_attempts.IP_FAILURE_LIMIT):
        login_attempts.register_failure("alvo@example.com", "198.51.100.9")

    with pytest.raises(HTTPException) as error:
        login(
            _request("198.51.100.9"),
            SimpleNamespace(username="alvo@example.com", password=CREDENCIAL_ERRADA),
            None,
            False,
        )
    assert error.value.status_code == 429
    assert "administrador" in error.value.detail


def test_correct_password_still_enters_after_foreign_failures(db, clean_state) -> None:
    user = _user(db)
    for _ in range(4):
        login_attempts.register_failure(user.email, "198.51.100.20")

    issued = login(
        _request("203.0.113.30"),
        SimpleNamespace(username=user.email, password=CREDENCIAL_DE_TESTE),
        db,
        False,
    )

    assert issued.user.id == user.id
    # O atraso aparece (a conta tem 4 falhas, já no teto), mas nunca impede a entrada.
    assert clean_state == [login_attempts.DELAY_CAP_SECONDS]
    assert login_attempts.delay_seconds(user.email) == 0.0


def test_wrong_password_reports_the_same_message_for_known_and_unknown_email(
    db, clean_state
) -> None:
    _user(db)
    details = []
    for email in ("qa@example.com", "nao-existe@example.com"):
        with pytest.raises(HTTPException) as error:
            login(
                _request("203.0.113.40"),
                SimpleNamespace(username=email, password=CREDENCIAL_ERRADA),
                db,
                False,
            )
        details.append(error.value.detail)
    assert details[0] == details[1] == "E-mail ou senha inválidos"


def test_unknown_email_still_verifies_a_discardable_hash(db, monkeypatch, clean_state) -> None:
    """S6 — o tempo de resposta não pode denunciar se a conta existe."""
    from app.api.routes import auth as auth_routes

    seen: list[str | None] = []

    def recorder(password: str, hashed: str | None) -> bool:
        seen.append(hashed)
        return False

    monkeypatch.setattr(auth_routes, "verify_password_always", recorder)
    with pytest.raises(HTTPException):
        login(
            _request("203.0.113.50"),
            SimpleNamespace(username="fantasma@example.com", password="qualquer"),
            db,
            False,
        )
    assert seen == [None]


def test_failures_do_not_accumulate_for_keys_outside_the_window(monkeypatch) -> None:
    now = _clock(monkeypatch)
    login_attempts.register_failure("conta@example.com", "198.51.100.60")
    now["value"] += login_attempts.WINDOW_SECONDS + 1
    assert login_attempts.snapshot()["delayed_accounts"] == []
    assert login_attempts.snapshot()["blocked_origins"] == []


def test_attempts_endpoints_require_users_manage_and_release_access(db, clean_state) -> None:
    from app.db.session import get_db
    from app.main import app

    admin = _user(db, role=UserRole.admin, email="admin@example.com")
    operator = _user(db, role=UserRole.operator, email="operador@example.com")
    login_attempts.register_failure("alvo@example.com", "198.51.100.70")
    for _ in range(login_attempts.IP_FAILURE_LIMIT - 1):
        login_attempts.register_failure("outro@example.com", "198.51.100.70")

    def override_db():
        yield db

    def token(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/auth/attempts").status_code == 401
            assert client.get("/api/v1/auth/attempts", headers=token(operator)).status_code == 403

            listed = client.get("/api/v1/auth/attempts", headers=token(admin))
            assert listed.status_code == 200
            body = listed.json()
            assert body["window_seconds"] == login_attempts.WINDOW_SECONDS
            assert [entry["ip"] for entry in body["blocked_origins"]] == ["198.51.100.70"]
            assert body["blocked_origins"][0]["failures"] == login_attempts.IP_FAILURE_LIMIT
            assert body["blocked_origins"][0]["seconds_left"] > 0
            delayed = {entry["email"] for entry in body["delayed_accounts"]}
            assert delayed == {"alvo@example.com", "outro@example.com"}

            no_target = client.post(
                "/api/v1/auth/attempts/reset",
                headers=token(admin),
                json={},
            )
            assert no_target.status_code == 422

            released = client.post(
                "/api/v1/auth/attempts/reset",
                headers=token(admin),
                json={"ip": "198.51.100.70"},
            )
            assert released.status_code == 200
            assert released.json()["blocked_origins"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)
