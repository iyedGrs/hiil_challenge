"""Authentication routes (spec/backend.md B8, B9).

Login issues a server-side session plus a per-session CSRF token; the session ID
travels only in the HttpOnly ``sid`` cookie. Invalid credentials produce one
uniform error whether or not the account exists, so the endpoint cannot be used
to enumerate users. Rate limiting is out of scope for this slice.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import CsrfDep, DbDep, SessionDep, UserDep
from app.config import SESSION_COOKIE_NAME
from app.errors import UNAUTHENTICATED, ApiError
from app.models.user import User
from app.schemas.auth import LoginRequest, SessionOut, UserOut
from app.security import (
    SCRYPT_DKLEN,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    SCRYPT_SALT_BYTES,
    SCRYPT_SCHEME,
    clear_session_cookie,
    create_session,
    revoke_session,
    set_session_cookie,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

#: One message for every credential failure (spec/backend.md B9).
INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."


@lru_cache(maxsize=1)
def _timing_equalizer_hash() -> str:
    """Well-formed digest that never matches any password.

    Verified when the account is unknown so an unknown email and a wrong password
    cost roughly the same time, removing a timing oracle for enumeration.
    """
    salt = base64.b64encode(bytes(SCRYPT_SALT_BYTES)).decode("ascii")
    digest = base64.b64encode(bytes(SCRYPT_DKLEN)).decode("ascii")
    return f"{SCRYPT_SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt}${digest}"


def _user_out(user: User) -> UserOut:
    """Project a user row onto the public contract shape (spec/backend.md B9)."""
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
    )


@router.post(
    "/login",
    response_model=SessionOut,
    summary="Sign in and receive a session cookie plus CSRF token",
)
def login(payload: LoginRequest, response: Response, db: DbDep) -> SessionOut:
    """Authenticate and start a session (spec/backend.md B9 ``POST /auth/login``).

    Raises:
        ApiError: 401 ``UNAUTHENTICATED`` with a uniform message for an unknown
            account, a wrong password or a deactivated account.
    """
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))

    if user is None:
        verify_password(payload.password, _timing_equalizer_hash())
        raise ApiError(UNAUTHENTICATED, INVALID_CREDENTIALS_MESSAGE)

    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise ApiError(UNAUTHENTICATED, INVALID_CREDENTIALS_MESSAGE)

    session_row = create_session(db, user)
    set_session_cookie(response, session_row.id)
    return SessionOut(user=_user_out(user), csrf_token=session_row.csrf_token)


@router.get("/me", response_model=SessionOut, summary="Current session and CSRF token")
def me(user: UserDep, session_row: SessionDep) -> SessionOut:
    """Return ``{user, csrf_token}`` for the live session (B9 ``GET /auth/me``).

    Answers 401 ``UNAUTHENTICATED`` when no valid session cookie is present, so
    the UI can distinguish "signed out" from "forbidden".
    """
    return SessionOut(user=_user_out(user), csrf_token=session_row.csrf_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Revoke the current session",
)
def logout(request: Request, db: DbDep, _csrf: CsrfDep) -> Response:
    """Revoke the session server-side and clear the cookie (B9, 204).

    Requires a valid CSRF token: a forged cross-site logout is still a state
    change (spec/backend.md B8).
    """
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    result = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(result)
    return result
