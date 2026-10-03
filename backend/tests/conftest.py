import os
from collections.abc import Generator
from cryptography.fernet import Fernet

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-longer-than-32-characters")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import entities  # noqa: F401


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
