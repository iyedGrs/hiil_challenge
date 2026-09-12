"""Test fixtures (spec/local-dev.md L2, L5, spec/backend.md B11).

The suite runs against a dedicated PostgreSQL database taken from
``TEST_DATABASE_URL``, or ``DATABASE_URL`` with ``_test`` appended to the database
name. The schema is created with ``Base.metadata.create_all`` rather than Alembic
so tests stay fast; ``migrations/versions/0001_initial.py`` is verified by running
``alembic upgrade head`` against a real database.

Each test runs inside an outer transaction that is rolled back afterwards, so the
API and the test observe the same rows without leaking state between tests.

No test performs a network or AI provider call.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

#: Used when neither environment variable is set: matches the Compose defaults
#: from spec/local-dev.md L3 with the ``_test`` database suffix applied.
DEFAULT_DATABASE_URL = "postgresql+psycopg://dispute_demo:dispute_demo@localhost:5432/dispute_demo"

DEMO_PREPARER_EMAIL = "preparer1@demo.local"
DEMO_REVIEWER_EMAIL = "reviewer@demo.local"
DEMO_PASSWORD = "demo-pass-1234"


def _with_test_suffix(url: str) -> str:
    """Append ``_test`` to the database name in ``url``."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if path.endswith("_test"):
        return url
    return urlunsplit(parts._replace(path=f"{path}_test"))


def resolve_test_database_url() -> str:
    """Return the database URL the suite should use.

    ``TEST_DATABASE_URL`` wins. Otherwise ``DATABASE_URL`` is reused with
    ``_test`` appended so a careless run cannot wipe development data.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    return _with_test_suffix(os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def storage_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Private file storage root for the API under test (spec/backend.md B4)."""
    return tmp_path_factory.mktemp("private-storage")


@pytest.fixture(scope="session")
def engine(storage_root: Path) -> Iterator[Engine]:
    """Session-wide engine with the schema created.

    Skips the suite when no test database is reachable: a missing local database
    is an environment gap, not a code failure, and the message names exactly what
    to set.
    """
    url = resolve_test_database_url()

    # Point the application at the test database and storage before any module
    # reads the cached settings.
    os.environ["DATABASE_URL"] = url
    os.environ["FILE_STORAGE_ROOT"] = str(storage_root)
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("AI_MODE", "fixture")
    os.environ.setdefault("SESSION_SECRET", "test-only-secret")
    os.environ.setdefault("COOKIE_SECURE", "false")

    from app.config import reset_settings_cache
    from app.db import reset_engine_cache
    from app.models import Base

    reset_settings_cache()
    reset_engine_cache()

    test_engine = create_engine(url, future=True)
    try:
        with test_engine.connect():
            pass
    except SQLAlchemyError as exc:
        test_engine.dispose()
        pytest.skip(
            "No test database reachable at the configured URL. Set TEST_DATABASE_URL "
            f"(or DATABASE_URL) to a PostgreSQL instance. Cause: {type(exc).__name__}",
            allow_module_level=True,
        )

    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
        reset_engine_cache()


@pytest.fixture()
def db(engine: Engine) -> Iterator[Session]:
    """Yield a clean session inside a transaction that is rolled back.

    ``join_transaction_mode="create_savepoint"`` lets application code commit
    normally while the outer transaction still discards everything afterwards.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        future=True,
    )
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    """TestClient whose requests share the test session."""
    from app.api.deps import get_db
    from app.main import create_app

    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        # Commit so route behaviour matches production; the fixture's outer
        # transaction still rolls the data back. The session is not closed here
        # because the fixture owns its lifetime.
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db: Session) -> None:
    """Seed the documented demo accounts (spec/local-dev.md L5)."""
    from app.seed_demo import seed

    seed(db, password=DEMO_PASSWORD)
    db.commit()
