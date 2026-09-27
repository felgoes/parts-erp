import argparse

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, UserRole


def bootstrap_admin() -> None:
    settings = get_settings()
    password = settings.bootstrap_admin_password
    if not password or len(password.get_secret_value()) < 12:
        raise SystemExit("Defina BOOTSTRAP_ADMIN_PASSWORD com pelo menos 12 caracteres")
    email = settings.bootstrap_admin_email.lower().strip()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("Usuário administrador já existe")
        db.add(
            User(
                email=email,
                full_name="Administrador",
                password_hash=hash_password(password.get_secret_value()),
                role=UserRole.admin,
            )
        )
        db.commit()
    print(f"Administrador {email} criado com sucesso")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap-admin"])
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        bootstrap_admin()


if __name__ == "__main__":
    main()
