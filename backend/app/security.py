"""Password hashing, server sessions and CSRF tokens (spec/backend.md B8).

Sessions are rows in ``sessions``, referenced by an HttpOnly ``sid`` cookie with
an explicit ``SameSite`` policy; ``Secure`` follows ``COOKIE_SECURE`` because
plain HTTP is a local development exception only (spec/local-dev.md L1).

Passwords use the standard library's scrypt with a per-user random salt, stored
as ``scrypt$n$r$p$salt_b64$hash_b64`` so parameters can be raised later without
invalidating existing rows. Verification is constant-time. No third-party
password library is used.

Nothing here logs a password, a session ID or a CSRF token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PATH,
    SESSION_COOKIE_SAMESITE,
    get_settings,
)
from app.ids import SESSION_PREFIX, new_id
from app.models.user import Session as SessionRow
from app.models.user import User

#: scrypt work factors. ``n`` is the CPU/memory cost, ``r`` the block size and
#: ``p`` the parallelisation factor. ``maxmem`` must fit 128 * n * r bytes.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_BYTES = 16
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

#: Marker prefix of the stored hash format.
SCRYPT_SCHEME = "scrypt"

#: CSRF token entropy in bytes (spec/backend.md B8).
CSRF_TOKEN_BYTES = 24


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    """Return a self-describing scrypt digest for ``password``.

    Returns:
        ``scrypt$n$r$p$salt_b64$hash_b64``. The plaintext is not retained.
    """
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return "$".join(
        [
            SCRYPT_SCHEME,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Verify ``password`` against a stored digest in constant time.

    A malformed or unknown-scheme digest returns ``False`` rather than raising,
    so a corrupt row cannot be distinguished from a wrong password.
    """
    try:
        scheme, n_text, r_text, p_text, salt_b64, hash_b64 = stored.split("$")
        if scheme != SCRYPT_SCHEME:
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    try:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


def issue_csrf_token() -> str:
    """Return a fresh per-session CSRF token (spec/backend.md B8)."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def verify_csrf(session_row: SessionRow, presented: str | None) -> bool:
    """Compare a presented CSRF token with the session's token.

    Returns ``False`` for a missing token; comparison is constant-time.
    """
    if not presented:
        return False
    return hmac.compare_digest(session_row.csrf_token, presented)


def session_ttl() -> timedelta:
    """Configured session lifetime; defaults to 12 hours (spec/backend.md B8)."""
    return timedelta(seconds=get_settings().session_ttl_seconds)


def create_session(db: DbSession, user: User) -> SessionRow:
    """Create and persist a server-side session for ``user``.

    The caller sets the cookie with :func:`set_session_cookie` and commits.
    """
    now = datetime.now(tz=timezone.utc)
    row = SessionRow(
        id=new_id(SESSION_PREFIX),
        user_id=user.id,
        csrf_token=issue_csrf_token(),
        expires_at=now + session_ttl(),
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row


def load_session(db: DbSession, session_id: str | None) -> SessionRow | None:
    """Return a live session for ``session_id``, or ``None``.

    A session is live when it exists, is not revoked, has not expired and its
    user is still active. Expiry is evaluated server-side, so a stale cookie
    grants nothing.
    """
    if not session_id:
        return None
    now = datetime.now(tz=timezone.utc)
    row = db.scalar(
        select(SessionRow).where(
            SessionRow.id == session_id,
            SessionRow.revoked_at.is_(None),
            SessionRow.expires_at > now,
        )
    )
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.last_seen_at = now
    return row


def revoke_session(db: DbSession, session_id: str | None) -> None:
    """Revoke ``session_id`` if it exists. Idempotent."""
    if not session_id:
        return
    row = db.get(SessionRow, session_id)
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = datetime.now(tz=timezone.utc)


def set_session_cookie(response: object, session_id: str) -> None:
    """Attach the HttpOnly ``sid`` cookie to ``response``.

    ``response`` is a Starlette response; typed loosely to keep this module free
    of a framework import cycle. Cookie flags come from settings so a deployed
    environment gets ``Secure`` while local HTTP does not (spec/local-dev.md L1).
    """
    settings = get_settings()
    response.set_cookie(  # type: ignore[attr-defined]
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=int(session_ttl().total_seconds()),
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_session_cookie(response: object) -> None:
    """Remove the ``sid`` cookie using the same path/flags it was set with."""
    settings = get_settings()
    response.delete_cookie(  # type: ignore[attr-defined]
        key=SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=SESSION_COOKIE_SAMESITE,
    )
