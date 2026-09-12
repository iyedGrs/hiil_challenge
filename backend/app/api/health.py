"""Health endpoints (spec/backend.md B9, spec/local-dev.md L6).

``/health/live`` reports on the process only. ``/health/ready`` additionally
proves the database answers, the Alembic schema is applied and the private file
storage root is writable. Neither performs a paid provider call, in fixture or
live mode (spec/local-dev.md L3).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbDep
from app.config import get_settings
from app.db import check_database, schema_revision
from app.schemas.common import ResponseModel

router = APIRouter(prefix="/health", tags=["health"])


class LiveOut(ResponseModel):
    """``GET /api/health/live`` body."""

    status: Literal["ok"]


class ReadyChecks(ResponseModel):
    """Per-dependency readiness detail. Values are ``ok`` or a short reason."""

    database: str
    schema_version: str | None
    storage: str


class ReadyOut(ResponseModel):
    """``GET /api/health/ready`` body."""

    status: Literal["ok", "unavailable"]
    checks: ReadyChecks


@router.get("/live", response_model=LiveOut, summary="Liveness: process only")
def live() -> LiveOut:
    """Return 200 while the API process is serving requests.

    No database, storage or provider access, so a dependency outage does not
    restart a healthy process (spec/local-dev.md L6).
    """
    return LiveOut(status="ok")


def _check_storage(root: str) -> str:
    """Return ``ok`` when ``root`` exists and accepts a write, else a reason."""
    path = Path(root)
    if not path.is_dir():
        return "missing"
    if not os.access(path, os.W_OK):
        return "not_writable"
    probe = path / f".readyz-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"")
    except OSError:
        return "not_writable"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return "ok"


@router.get(
    "/ready",
    response_model=ReadyOut,
    summary="Readiness: database, schema and private storage",
)
def ready(db: DbDep, response: Response) -> ReadyOut:
    """Verify database, applied schema and writable storage.

    Returns 503 with the failing detail when any check fails; a reachable
    database with no migrations applied is not ready (spec/local-dev.md L4).
    Failure detail names the dependency only, never credentials or paths that
    would disclose secrets.
    """
    settings = get_settings()

    database_state = "ok"
    revision: str | None = None
    try:
        check_database(db)
        revision = schema_revision(db)
        if revision is None:
            database_state = "schema_missing"
    except SQLAlchemyError:
        database_state = "unavailable"

    storage_state = _check_storage(settings.file_storage_root)
    healthy = database_state == "ok" and storage_state == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyOut(
        status="ok" if healthy else "unavailable",
        checks=ReadyChecks(
            database=database_state,
            schema_version=revision,
            storage=storage_state,
        ),
    )
