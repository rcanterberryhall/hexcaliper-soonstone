"""SQLAlchemy engine factory with a pragma listener.

The pragma listener fires on every new SQLite connection (including pool reuses
that opened a fresh connection). It MUST set foreign_keys, journal_mode,
synchronous, cache_size, temp_store, mmap_size, busy_timeout per the soonstone
roadmap's Required SQLite pragmas section.

Note: PRAGMA auto_vacuum is NOT here — it must be set inside the very first
migration before any table exists, and re-asserting it on a populated DB has no
effect.
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all soonstone ORM models."""


_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    ("cache_size", "-64000"),
    ("temp_store", "MEMORY"),
    ("mmap_size", "268435456"),
    ("busy_timeout", "5000"),
)


def create_engine_with_pragmas(database_url: str, **engine_kwargs) -> Engine:
    """Create a SQLAlchemy engine with the soonstone pragma listener attached.

    Only attaches the listener for sqlite:// URLs. For other dialects (the
    one-day Postgres migration path), the listener is a no-op.
    """
    engine = create_engine(database_url, **engine_kwargs)

    if engine.url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                for pragma, value in _PRAGMAS:
                    cursor.execute(f"PRAGMA {pragma} = {value}")
            finally:
                cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
