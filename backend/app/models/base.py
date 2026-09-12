"""Declarative base and shared column helpers (spec/backend.md B7, B8).

Conventions enforced here:

* Monetary columns use ``Numeric(18, 3)``; PostgreSQL money values are never
  floats (B7).
* Timestamps are ``DateTime(timezone=True)`` and stored in UTC (B9).
* Public opaque IDs are the primary keys, so routes address rows directly (B9).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, MetaData, Numeric, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

#: Deterministic constraint names keep hand-written migrations readable.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Public ID column width: longest prefix (``CASE_``) plus ten hex characters.
ID_LENGTH = 32

#: Monetary precision for TND: 12 integer digits and 3 fractional digits (B3).
MONEY_PRECISION = 18
MONEY_SCALE = 3

#: Money column type. Declared once so no model can reach for Float (B7).
Money = Numeric(MONEY_PRECISION, MONEY_SCALE, asdecimal=True)

#: Width of enum-backed VARCHAR columns.
ENUM_LENGTH = 48


def enum_type(enum_cls: type[Enum]) -> SAEnum:
    """Return a portable VARCHAR-backed enum type.

    Native PostgreSQL enums would require a migration for every added value, so
    values are stored as text. Unknown values are rejected at the API edge
    (spec/backend.md B9) and by ``validate_strings`` here.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=ENUM_LENGTH,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class JsonType(TypeDecorator[Any]):
    """JSONB on PostgreSQL, JSON elsewhere.

    Keeps ``Base.metadata.create_all`` usable on other backends for fast tests
    while production uses JSONB (spec/local-dev.md L2 backend/tests).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:  # noqa: ANN401 - SQLAlchemy hook
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    """Declarative base holding the shared metadata (spec/backend.md B8)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Return an aware UTC timestamp. All stored timestamps are UTC (B9)."""
    return datetime.now(tz=timezone.utc)


def id_column(*, primary_key: bool = True) -> Mapped[str]:
    """Public opaque ID column (spec/backend.md B9)."""
    return mapped_column(String(ID_LENGTH), primary_key=primary_key)


def created_at_column() -> Mapped[datetime]:
    """Server-side creation timestamp; client clocks are never trusted (B9)."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utcnow,
    )


def updated_at_column() -> Mapped[datetime]:
    """Server-side update timestamp; not a concurrency token (B9)."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )


class TimestampMixin:
    """Adds ``created_at``/``updated_at`` to a model."""

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
