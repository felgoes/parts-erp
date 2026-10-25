import argparse
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, UserRole
from app.services.vehicle_fleet_import import import_latest_fleet


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
    parser.add_argument("command", choices=["bootstrap-admin", "import-fleet"])
    parser.add_argument("--file", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        bootstrap_admin()
    elif args.command == "import-fleet":
        if args.file is None or not args.file.is_file():
            raise SystemExit("Informe --file com o ZIP oficial da frota RENAVAM")
        with SessionLocal() as db:
            result = import_latest_fleet(
                db,
                force=args.force,
                archive_path=args.file,
            )
        print(result)


if __name__ == "__main__":
    main()
