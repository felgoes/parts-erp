from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.permissions import Permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User, UserRole
from app.schemas.common import (
    UserCreate,
    UserOut,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserUpdate,
)
from app.services.user_media import (
    MAX_USER_AVATAR_BYTES,
    store_user_avatar,
    user_avatar_path,
)

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.patch("/me/profile", response_model=UserOut)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    user.email = str(payload.email).lower().strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail") from exc
    db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserOut)
async def upload_my_avatar(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    contents = await image.read(MAX_USER_AVATAR_BYTES + 1)
    try:
        filename = store_user_avatar(contents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    previous = user.avatar_filename
    user.avatar_filename = filename
    db.commit()
    db.refresh(user)
    if previous:
        try:
            user_avatar_path(previous).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
    return user


@router.get("/me/avatar", response_class=FileResponse)
def read_my_avatar(user: User = Depends(get_current_user)) -> FileResponse:
    if not user.avatar_filename:
        raise HTTPException(status_code=404, detail="Foto de perfil não cadastrada")
    try:
        path: Path = user_avatar_path(user.avatar_filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Foto de perfil não encontrada") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Foto de perfil não encontrada")
    return FileResponse(
        path,
        media_type="image/jpeg",
        filename="avatar.jpg",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.full_name, User.email)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> User:
    user = User(
        email=payload.email.lower().strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail") from exc
    db.refresh(user)
    return user


@router.patch("/{user_id}/password", response_model=UserOut)
def reset_password(
    user_id: str,
    payload: UserPasswordUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    next_role = data.get("role", user.role)
    next_active = data.get("active", user.active)
    if actor.id == user.id and (next_role != UserRole.admin or not next_active):
        raise HTTPException(
            status_code=409,
            detail="Não é possível remover ou desativar seu próprio acesso de administrador",
        )
    is_removing_admin = (
        user.active
        and user.role == UserRole.admin
        and (next_role != UserRole.admin or not next_active)
    )
    if is_removing_admin:
        active_admin_ids = list(
            db.scalars(
                select(User.id)
                .where(User.active.is_(True), User.role == UserRole.admin)
                .order_by(User.id)
                .with_for_update()
            )
        )
        if user.id in active_admin_ids and len(active_admin_ids) <= 1:
            raise HTTPException(
                status_code=409, detail="Mantenha ao menos um administrador ativo no sistema"
            )
    if not data:
        raise HTTPException(status_code=422, detail="Informe ao menos um campo")
    if "email" in data:
        user.email = data["email"].lower().strip()
    if "full_name" in data:
        user.full_name = data["full_name"].strip()
    if "password" in data:
        user.password_hash = hash_password(data["password"])
    if "role" in data:
        user.role = data["role"]
    if "active" in data:
        user.active = data["active"]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail") from exc
    db.refresh(user)
    return user
