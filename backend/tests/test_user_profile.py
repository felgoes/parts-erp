import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.api.routes.users import read_my_avatar, update_my_profile, upload_my_avatar
from app.core.security import hash_password
from app.models import User, UserRole
from app.schemas.common import UserProfileUpdate


def user(db, email: str = "perfil@example.com") -> User:
    current = User(
        email=email,
        full_name="Usuário Perfil",
        password_hash=hash_password("senha-segura-123"),
        role=UserRole.admin,
    )
    db.add(current)
    db.commit()
    db.refresh(current)
    return current


def jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), color=(80, 120, 40)).save(output, format="JPEG")
    return output.getvalue()


def test_user_can_update_own_email(db) -> None:
    current = user(db)

    updated = update_my_profile(UserProfileUpdate(email="novo@example.com"), db, current)

    assert updated.email == "novo@example.com"


def test_duplicate_profile_email_is_rejected(db) -> None:
    current = user(db)
    user(db, "existente@example.com")

    with pytest.raises(HTTPException) as error:
        update_my_profile(UserProfileUpdate(email="existente@example.com"), db, current)

    assert error.value.status_code == 409


def test_user_can_upload_and_read_avatar(db, monkeypatch, tmp_path) -> None:
    current = user(db)
    monkeypatch.setattr(
        "app.services.user_media.get_settings",
        lambda: SimpleNamespace(product_images_dir=str(tmp_path)),
    )
    upload = UploadFile(filename="perfil.jpg", file=BytesIO(jpeg()))

    updated = asyncio.run(upload_my_avatar(upload, db, current))
    response = read_my_avatar(updated)

    assert updated.avatar_filename and updated.avatar_filename.endswith(".jpg")
    assert Path(response.path) == tmp_path / "avatars" / updated.avatar_filename
