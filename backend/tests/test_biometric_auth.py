import pytest
from fastapi import HTTPException

from app.api.routes.auth import biometric_login, create_biometric_credential
from app.core.security import hash_password
from app.models import User, UserRole
from app.schemas.common import BiometricCredentialCreate, BiometricCredentialLogin


def _user(db) -> User:
    user = User(
        email="biometria@example.com",
        full_name="Usuário Biométrico",
        password_hash=hash_password("uma-senha-segura"),
        role=UserRole.operator,
        active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_biometric_credential_creates_a_new_session(db) -> None:
    user = _user(db)
    enrollment = create_biometric_credential(
        BiometricCredentialCreate(device_name="Galaxy S23"), user
    )

    session = biometric_login(
        BiometricCredentialLogin(credential=enrollment.credential), db
    )

    assert session.user.id == user.id
    assert session.access_token
    assert enrollment.credential not in user.password_hash


def test_password_change_revokes_biometric_credential(db) -> None:
    user = _user(db)
    enrollment = create_biometric_credential(
        BiometricCredentialCreate(device_name="Galaxy S23"), user
    )
    user.password_hash = hash_password("uma-nova-senha-segura")
    db.commit()

    with pytest.raises(HTTPException) as error:
        biometric_login(BiometricCredentialLogin(credential=enrollment.credential), db)

    assert error.value.status_code == 401
