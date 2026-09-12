"""Users, server sessions and reviewer recipients (spec/backend.md B8, B9, B10).

Roles are assigned by the server; there is no privileged client role flag and no
shared role switcher in integrated mode (B8). Sessions are server-side rows so a
logout or expiry is authoritative rather than advisory.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import Role
from app.models.base import (
    Base,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class User(Base, TimestampMixin):
    """Account with a server-assigned role (spec/backend.md B8).

    ``password_hash`` holds a self-describing stdlib scrypt digest produced by
    :mod:`app.security`; the plaintext is never stored or logged.
    """

    __tablename__ = "users"

    id: Mapped[str] = id_column()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Role] = mapped_column(enum_type(Role), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_role", "role"),)


class Session(Base):
    """Server-side session backing the HttpOnly ``sid`` cookie (B8).

    Each session carries its own CSRF token; mutations must present it in the
    ``X-CSRF-Token`` header. Session IDs are secrets and are never logged.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = id_column()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class Recipient(Base, TimestampMixin):
    """Authorized reviewer destination for ``GET /api/recipients`` (B9, B10).

    Submission targets are server-owned rows, so a preparer cannot submit to an
    arbitrary email address. ``remit`` is a descriptive label and must not claim
    official filing or legal acceptance (B10).
    """

    __tablename__ = "recipients"

    id: Mapped[str] = id_column()
    reviewer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    remit: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    reviewer: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("reviewer_id", "label", name="uq_recipients_reviewer_id_label"),
        Index("ix_recipients_reviewer_id", "reviewer_id"),
    )
