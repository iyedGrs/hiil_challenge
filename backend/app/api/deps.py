"""Shared route dependencies (spec/backend.md B8, B9).

Authorization is server-side on every request: the session cookie is resolved to
a row, the role comes from the database and CSRF is enforced on every unsafe
method. No client-supplied role flag is honoured (B8).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from app.config import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.db import get_session_factory
from app.domain.enums import Role
from app.errors import csrf_invalid, not_found, unauthenticated
from app.models.user import Session as SessionRow
from app.models.user import User
from app.security import load_session, verify_csrf

#: Methods that require a CSRF token (spec/backend.md B8).
UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Login is the only unsafe route exempt from CSRF: no session exists yet.
CSRF_EXEMPT_PATHS: frozenset[str] = frozenset({"/api/auth/login"})


def get_db() -> Iterator[DbSession]:
    """Yield a request-scoped session, committing on success.

    A failed request rolls back, so a partially applied revision change can
    never be observed (spec/backend.md B7, B9).
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


DbDep = Annotated[DbSession, Depends(get_db)]


def current_session(request: Request, db: DbDep) -> SessionRow:
    """Resolve the ``sid`` cookie to a live session row.

    Raises:
        ApiError: 401 ``UNAUTHENTICATED`` when the cookie is missing, unknown,
            revoked or expired (spec/backend.md B9).
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    row = load_session(db, session_id)
    if row is None:
        raise unauthenticated()
    return row


SessionDep = Annotated[SessionRow, Depends(current_session)]


def current_user(db: DbDep, session_row: SessionDep) -> User:
    """Return the signed-in user.

    Raises:
        ApiError: 401 ``UNAUTHENTICATED`` when the session's user vanished or was
            deactivated between requests.
    """
    user = db.get(User, session_row.user_id)
    if user is None or not user.is_active:
        raise unauthenticated()
    return user


UserDep = Annotated[User, Depends(current_user)]


def require_csrf(request: Request, session_row: SessionDep) -> None:
    """Enforce ``X-CSRF-Token`` on unsafe methods (spec/backend.md B8).

    Safe methods pass through. ``POST /api/auth/login`` is exempt because no
    session exists before it runs; every other mutation must present the token
    issued with the session.

    Raises:
        ApiError: 403 ``CSRF_INVALID`` when the header is absent or mismatched.
    """
    if request.method.upper() not in UNSAFE_METHODS:
        return
    if request.url.path in CSRF_EXEMPT_PATHS:
        return
    presented = request.headers.get(CSRF_HEADER_NAME)
    if not verify_csrf(session_row, presented):
        raise csrf_invalid()


CsrfDep = Annotated[None, Depends(require_csrf)]


def require_role(*roles: Role) -> Callable[[User], User]:
    """Build a dependency asserting the signed-in user holds one of ``roles``.

    Case-scoped resources answer 404 rather than 403 so a preparer cannot probe
    another owner's case IDs (spec/backend.md B9).
    """
    allowed = frozenset(roles)

    def _dependency(user: UserDep) -> User:
        if user.role not in allowed:
            raise not_found()
        return user

    return _dependency


#: Ready-made role guards for the routers added by later slices.
require_preparer = require_role(Role.preparer)
require_reviewer = require_role(Role.reviewer)

PreparerDep = Annotated[User, Depends(require_preparer)]
ReviewerDep = Annotated[User, Depends(require_reviewer)]
