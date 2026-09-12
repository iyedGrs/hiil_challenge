"""Database engine and session management (spec/backend.md B8).

A synchronous SQLAlchemy 2.0 engine over ``psycopg`` v3 backs both the API
process and the worker. Migrations are never executed here: the deployment runs
a single ``alembic upgrade head`` step before starting processes
(spec/local-dev.md L4).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

#: Alembic writes this table; readiness uses it to prove the schema is applied.
ALEMBIC_VERSION_TABLE = "alembic_version"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide engine.

    ``pool_pre_ping`` keeps long-lived worker connections usable after a
    database restart, which Compose health checks alone do not guarantee
    (spec/local-dev.md L4).
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on failure.

    Used by the worker and the seed script; the API uses ``app.api.deps.get_db``.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(session: Session) -> None:
    """Raise if the database does not answer a trivial query.

    Part of ``GET /api/health/ready`` (spec/backend.md B9).
    """
    session.execute(text("SELECT 1"))


def schema_revision(session: Session) -> str | None:
    """Return the applied Alembic revision, or ``None`` when unmigrated.

    ``GET /api/health/ready`` must report the schema as usable, not merely the
    database as reachable (spec/backend.md B9).

    Table presence is checked with the inspector rather than by letting a query
    fail: on PostgreSQL a failed statement aborts the surrounding transaction,
    which would break the rest of the readiness check.
    """
    connection = session.connection()
    if not inspect(connection).has_table(ALEMBIC_VERSION_TABLE):
        return None
    row = session.execute(
        text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE} LIMIT 1")
    ).first()
    return None if row is None else str(row[0])


def reset_engine_cache() -> None:
    """Dispose and forget the cached engine. Used by tests."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
