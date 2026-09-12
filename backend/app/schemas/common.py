"""Shared schema bases and envelopes (spec/backend.md B9).

Contract rules encoded here: unknown fields are rejected, amounts are decimal
strings (never JSON floats), timestamps are UTC ISO 8601, success objects are
direct JSON and lists use ``{items, next_cursor}``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_serializer

#: Integer/fraction digit budget for TND amounts (spec/backend.md B3).
MAX_AMOUNT_INTEGER_DIGITS = 12
MAX_AMOUNT_FRACTION_DIGITS = 3


class StrictModel(BaseModel):
    """Base for request bodies: extra fields are a validation error (B3, B9)."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        populate_by_name=False,
        use_enum_values=False,
    )


class ResponseModel(BaseModel):
    """Base for response bodies.

    Extra fields are also forbidden so a response can never leak a field that is
    not part of the contract.
    """

    model_config = ConfigDict(extra="forbid", ser_json_timedelta="iso8601")


class ErrorDetail(ResponseModel):
    """One ``{field, message}`` entry (spec/backend.md B9)."""

    field: str
    message: str


class ErrorBody(ResponseModel):
    """Body of the error envelope (spec/backend.md B9)."""

    code: str
    message: str
    field_errors: list[ErrorDetail] = []
    retryable: bool = False


class ErrorResponse(ResponseModel):
    """Full error envelope: ``{"error": {...}}`` (spec/backend.md B9)."""

    error: ErrorBody


ItemT = TypeVar("ItemT")


class ListResponse(ResponseModel, Generic[ItemT]):
    """Cursor-paginated list envelope ``{items, next_cursor}`` (B9)."""

    items: list[ItemT]
    next_cursor: str | None = None


class MoneyMixin(BaseModel):
    """Serialises ``Decimal`` fields as canonical decimal strings (B7, B9)."""

    @field_serializer("*", when_used="json")
    def _serialize_decimals(self, value: object) -> object:
        if isinstance(value, Decimal):
            return format(value, "f")
        return value


def decimal_to_string(value: Decimal) -> str:
    """Render a ``Decimal`` as a canonical, non-exponential decimal string."""
    return format(value, "f")
