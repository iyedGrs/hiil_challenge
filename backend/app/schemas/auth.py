"""Authentication schemas (spec/backend.md B9 ``/auth/*``).

``POST /auth/login`` and ``GET /auth/me`` return the same
``{user, csrf_token}`` shape. Credentials are never echoed back and the failure
message is uniform so accounts cannot be enumerated.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from app.domain.enums import Role
from app.schemas.common import ResponseModel, StrictModel

#: Conservative address shape. Deliverability is not validated here: the login
#: outcome must not depend on anything beyond credential verification (B9).
EmailStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+$",
    ),
]


class LoginRequest(StrictModel):
    """``POST /api/auth/login`` body: ``{email, password}`` (B9).

    Extra fields are rejected with 422 ``INVALID_INPUT``.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(ResponseModel):
    """Public view of the signed-in account (spec/backend.md B9).

    The password hash and session ID are deliberately absent.
    """

    id: str
    email: str
    role: Role
    display_name: str


class SessionOut(ResponseModel):
    """``{user, csrf_token}`` returned by login and ``/auth/me`` (B9).

    The session ID itself stays in the HttpOnly cookie; only the CSRF token is
    readable by the browser application (B8).
    """

    user: UserOut
    csrf_token: str
