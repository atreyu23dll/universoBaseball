"""Motor, sesión y tipos portables entre PostgreSQL y SQLite."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import JSON, Numeric, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

#: JSON en SQLite, JSONB en PostgreSQL. Una sola definición de modelo.
JSONType = JSON().with_variant(JSONB, "postgresql")
#: El dinero nunca es `float`. Ver ADR 0002.
MoneyType = Numeric(16, 2)


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return uuid.uuid4().hex


def _build_engine():
    settings = get_settings()
    kwargs: dict = {"echo": settings.sql_echo, "future": True}
    if settings.is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    engine = create_engine(settings.database_url, **kwargs)

    if settings.is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - E/S
            cursor = dbapi_connection.cursor()
            # Las claves externas están apagadas por omisión en SQLite: sin
            # esto, la integridad referencial del modelo sería decorativa.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Unidad de trabajo para procesos fuera de una petición HTTP."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
