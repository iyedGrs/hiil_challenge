"""Error envelope and exception handlers (spec/backend.md B9).

Every failure leaves the API as
``{"error": {"code", "message", "field_errors", "retryable"}}`` where
``field_errors`` is a list of ``{"field", "message"}``. Provider traces,
tracebacks and document contents are never included (B9, spec/local-dev.md L6).
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

# --- Contract codes (spec/backend.md B9) ---
UNSUPPORTED_CASE_TYPE: Final[str] = "UNSUPPORTED_CASE_TYPE"  # 422
INVALID_INPUT: Final[str] = "INVALID_INPUT"  # 422
FILE_LIMIT: Final[str] = "FILE_LIMIT"  # 413
UNSUPPORTED_FILE: Final[str] = "UNSUPPORTED_FILE"  # 415
REVISION_CONFLICT: Final[str] = "REVISION_CONFLICT"  # 409
INTAKE_NOT_READY: Final[str] = "INTAKE_NOT_READY"  # 409
ANALYSIS_NOT_PUBLISHED: Final[str] = "ANALYSIS_NOT_PUBLISHED"  # 409
ANALYSIS_OUTDATED: Final[str] = "ANALYSIS_OUTDATED"  # 409
ANALYSIS_ALREADY_RUNNING: Final[str] = "ANALYSIS_ALREADY_RUNNING"  # 409
BUDGET_EXHAUSTED: Final[str] = "BUDGET_EXHAUSTED"  # 429
PROVIDER_UNAVAILABLE: Final[str] = "PROVIDER_UNAVAILABLE"  # 503

# --- Access and protocol codes (spec/backend.md B8, B9) ---
UNAUTHENTICATED: Final[str] = "UNAUTHENTICATED"  # 401
NOT_FOUND: Final[str] = "NOT_FOUND"  # 404
FORBIDDEN: Final[str] = "FORBIDDEN"  # 403 (case resources answer 404 instead)
CSRF_INVALID: Final[str] = "CSRF_INVALID"  # 403
IDEMPOTENCY_CONFLICT: Final[str] = "IDEMPOTENCY_CONFLICT"  # 409
EXPORT_NOT_READY: Final[str] = "EXPORT_NOT_READY"  # 409
INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"  # 500

#: Default HTTP status for each contract code.
ERROR_STATUS: Final[dict[str, int]] = {
    UNSUPPORTED_CASE_TYPE: 422,
    INVALID_INPUT: 422,
    FILE_LIMIT: 413,
    UNSUPPORTED_FILE: 415,
    REVISION_CONFLICT: 409,
    INTAKE_NOT_READY: 409,
    ANALYSIS_NOT_PUBLISHED: 409,
    ANALYSIS_OUTDATED: 409,
    ANALYSIS_ALREADY_RUNNING: 409,
    BUDGET_EXHAUSTED: 429,
    PROVIDER_UNAVAILABLE: 503,
    UNAUTHENTICATED: 401,
    NOT_FOUND: 404,
    FORBIDDEN: 403,
    CSRF_INVALID: 403,
    IDEMPOTENCY_CONFLICT: 409,
    EXPORT_NOT_READY: 409,
    INTERNAL_ERROR: 500,
}

#: Codes a client may retry unchanged (spec/backend.md B8 rate/cost controls).
RETRYABLE_CODES: Final[frozenset[str]] = frozenset({PROVIDER_UNAVAILABLE, INTERNAL_ERROR})

#: Generic messages, so a handler never has to invent user-visible wording.
_DEFAULT_MESSAGES: Final[dict[str, str]] = {
    INVALID_INPUT: "The request body failed validation.",
    UNAUTHENTICATED: "Authentication is required.",
    NOT_FOUND: "The requested resource was not found.",
    FORBIDDEN: "This action is not allowed for the signed-in user.",
    CSRF_INVALID: "A valid CSRF token is required for this request.",
    INTERNAL_ERROR: "The request could not be completed.",
}

#: Status codes Starlette raises that map onto contract codes.
_HTTP_STATUS_TO_CODE: Final[dict[int, str]] = {
    401: UNAUTHENTICATED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    405: NOT_FOUND,
    409: REVISION_CONFLICT,
    413: FILE_LIMIT,
    415: UNSUPPORTED_FILE,
    422: INVALID_INPUT,
    429: BUDGET_EXHAUSTED,
    503: PROVIDER_UNAVAILABLE,
}


class FieldError(dict[str, str]):
    """A single ``{"field", "message"}`` entry in the error envelope."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(field=field, message=message)


class ApiError(Exception):
    """Domain failure carrying the contract envelope (spec/backend.md B9)."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        status: int | None = None,
        field_errors: list[FieldError] | list[dict[str, str]] | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code
        self.message = message or _DEFAULT_MESSAGES.get(code, "The request could not be completed.")
        self.status = status if status is not None else ERROR_STATUS.get(code, 400)
        self.field_errors: list[dict[str, str]] = [dict(entry) for entry in (field_errors or [])]
        self.retryable = retryable if retryable is not None else code in RETRYABLE_CODES
        super().__init__(f"{self.code}: {self.message}")

    def to_payload(self) -> dict[str, object]:
        """Return the JSON body for this error."""
        return error_payload(
            code=self.code,
            message=self.message,
            field_errors=self.field_errors,
            retryable=self.retryable,
        )


def error_payload(
    code: str,
    message: str,
    field_errors: list[dict[str, str]] | None = None,
    retryable: bool = False,
) -> dict[str, object]:
    """Build the canonical error envelope."""
    return {
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors or [],
            "retryable": retryable,
        }
    }


def unauthenticated(message: str | None = None) -> ApiError:
    """401 for a missing or expired session (spec/backend.md B9)."""
    return ApiError(UNAUTHENTICATED, message)


def not_found(message: str | None = None) -> ApiError:
    """404 used for inaccessible case resources so existence is not disclosed.

    spec/backend.md B9: "Use 401 when unauthenticated and 404 for inaccessible
    case resources to avoid disclosing existence."
    """
    return ApiError(NOT_FOUND, message)


def csrf_invalid(message: str | None = None) -> ApiError:
    """403 for a missing or mismatched CSRF token (spec/backend.md B8)."""
    return ApiError(CSRF_INVALID, message)


#: Location segments dropped when rendering a field path. ``body`` is Pydantic's
#: marker for "in the request body" and ``claim`` is the wrapper key used by
#: ``PATCH /cases/{id}/claim``. Removing both makes ``field_errors`` claim-relative
#: (``claimed_amount``, ``dates.invoice``), which is what the UI anchors a message
#: to its input with. ``query``/``path`` markers are kept, because there a client
#: does need to know the value did not come from the body.
_DROPPED_LOCATION_SEGMENTS: Final[frozenset[str]] = frozenset({"body", "claim"})


def _validation_field_path(location: tuple[object, ...]) -> str:
    """Render a Pydantic error location as a claim-relative dotted field path."""
    parts = [str(part) for part in location]
    while parts and parts[0] in _DROPPED_LOCATION_SEGMENTS:
        parts.pop(0)
    return ".".join(parts) if parts else "body"


def validation_field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    """Map Pydantic validation errors to contract ``field_errors``.

    The submitted input is never echoed back: an upload or narrative may contain
    document content (spec/backend.md B9).
    """
    field_errors: list[dict[str, str]] = []
    for error in exc.errors():
        location = tuple(error.get("loc", ()))
        field_errors.append(
            {
                "field": _validation_field_path(location),
                "message": str(error.get("msg", "Invalid value.")),
            }
        )
    return field_errors


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Serialise :class:`ApiError` into the contract envelope."""
    assert isinstance(exc, ApiError)  # registered only for ApiError
    return JSONResponse(status_code=exc.status, content=exc.to_payload())


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map ``RequestValidationError`` to 422 ``INVALID_INPUT``."""
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=ERROR_STATUS[INVALID_INPUT],
        content=error_payload(
            code=INVALID_INPUT,
            message=_DEFAULT_MESSAGES[INVALID_INPUT],
            field_errors=validation_field_errors(exc),
        ),
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map Starlette HTTP exceptions onto contract codes."""
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, INTERNAL_ERROR)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    message = detail or _DEFAULT_MESSAGES.get(code, "The request could not be completed.")
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=code,
            message=message,
            retryable=code in RETRYABLE_CODES,
        ),
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a sanitized 500. Tracebacks stay in server logs only."""
    logger.exception(
        "Unhandled error handling %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=ERROR_STATUS[INTERNAL_ERROR],
        content=error_payload(
            code=INTERNAL_ERROR,
            message=_DEFAULT_MESSAGES[INTERNAL_ERROR],
            retryable=True,
        ),
    )


def sanitize_error_message(exc: BaseException, limit: int = 200) -> str:
    """Return a short, content-free description of ``exc`` for storage.

    Job rows persist sanitized errors (spec/backend.md B8): the exception type
    plus a truncated message, never a traceback, provider payload or document
    text.
    """
    if isinstance(exc, ApiError):
        return f"{exc.code}: {exc.message}"[:limit]
    text = str(exc).strip().splitlines()
    first_line = text[0] if text else ""
    label = type(exc).__name__
    return (f"{label}: {first_line}" if first_line else label)[:limit]


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler to ``app`` (spec/backend.md B9)."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
