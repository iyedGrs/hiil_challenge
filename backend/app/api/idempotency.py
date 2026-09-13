"""Idempotency-key handling for job-creating routes (spec/backend.md B8, B9).

``POST /cases/{id}/analyses``, ``/exports`` and ``/submissions`` all carry an
idempotency header. The rules:

* Same key, same request -> return the original result. A retried request must not
  launch a second provider run (B8).
* Same key, different request -> ``409 IDEMPOTENCY_CONFLICT``. Silently returning
  the first result would answer a question nobody asked.
* The stored fingerprint is a SHA-256 over the canonical request, never the raw
  body, so no case content is retained in this table.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from fastapi import Header
from sqlalchemy.orm import Session as DbSession

from app.errors import IDEMPOTENCY_CONFLICT, ApiError
from app.models.job import IdempotencyKey

#: Header carrying the client-supplied key (spec/backend.md B9).
IDEMPOTENCY_HEADER_NAME: Final[str] = "Idempotency-Key"

#: Bound on an accepted key, long enough for a UUID or ULID.
MAX_KEY_LENGTH: Final[int] = 200

#: Operation scopes, matching ``IdempotencyKey.scope``.
SCOPE_ANALYSIS: Final[str] = "analysis"
SCOPE_EXPORT: Final[str] = "export"
SCOPE_SUBMISSION: Final[str] = "submission"


def idempotency_key_header(
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER_NAME),
) -> str | None:
    """FastAPI dependency reading and bounding the idempotency header."""
    if idempotency_key is None:
        return None
    key = idempotency_key.strip()
    if not key:
        return None
    return key[:MAX_KEY_LENGTH]


def fingerprint(payload: dict[str, Any]) -> str:
    """Return a stable SHA-256 over the canonical request payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reuse_or_claim(
    db: DbSession,
    *,
    case_id: str,
    scope: str,
    key: str | None,
    request_fingerprint: str,
) -> tuple[IdempotencyKey | None, bool]:
    """Look up or record ``key`` for ``(case_id, scope)``.

    Args:
        key: The client-supplied key. ``None`` disables replay protection for this
            request, which is allowed: the header is how a client opts in.

    Returns:
        ``(row, is_replay)``. On a replay the caller returns the recorded result
        instead of creating new work.

    Raises:
        ApiError: 409 ``IDEMPOTENCY_CONFLICT`` when the key was used for a
            different request.
    """
    if key is None:
        return None, False

    existing = db.get(IdempotencyKey, (case_id, scope, key))
    if existing is not None:
        if existing.request_fingerprint != request_fingerprint:
            raise ApiError(
                IDEMPOTENCY_CONFLICT,
                "This idempotency key was already used for a different request.",
            )
        return existing, True

    row = IdempotencyKey(
        case_id=case_id,
        scope=scope,
        key=key,
        request_fingerprint=request_fingerprint,
    )
    db.add(row)
    db.flush()
    return row, False
