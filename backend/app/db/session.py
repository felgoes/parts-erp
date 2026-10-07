import logging
from collections.abc import Generator
from functools import lru_cache

from redis import Redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
logger = logging.getLogger(__name__)


@lru_cache
def _change_publisher() -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)


@event.listens_for(SessionLocal, "before_flush")
def _mark_changed(session: Session, _flush_context: object, _instances: object) -> None:
    if session.new or session.dirty or session.deleted:
        session.info["erp_data_changed"] = True


@event.listens_for(SessionLocal, "after_commit")
def _publish_change(session: Session) -> None:
    if not session.info.pop("erp_data_changed", False):
        return
    try:
        _change_publisher().publish("parts-erp:changes", "update")
    except Exception:  # Live views must never make a committed sale fail.
        logger.exception("Could not publish ERP data change")


@event.listens_for(SessionLocal, "after_rollback")
def _discard_change(session: Session) -> None:
    session.info.pop("erp_data_changed", None)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
