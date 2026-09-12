"""``GET /api/config`` (spec/backend.md B9).

Publishes the enumerated vocabulary, ingestion limits, current legal coverage and
execution mode. No authentication is required: the UI needs this before a session
exists, and nothing here is case data or a secret.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.domain.enums import (
    CaseType,
    Currency,
    ExecutionMode,
    LegalCoverage,
    RequestedOutcome,
)
from app.schemas.config import ConfigOut, LimitsOut

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigOut, summary="Client bootstrap configuration")
def read_config() -> ConfigOut:
    """Return the contract vocabulary and limits (spec/backend.md B9).

    ``legal_coverage`` is reported as ``unvalidated`` in this slice: no reviewed
    legal pack is loaded yet, and B5 requires that claims of legal-requirement
    verification stay disabled until one is. The legal-pack slice replaces this
    with the loaded pack's coverage.

    ``execution_mode`` mirrors ``AI_MODE`` so the UI can label fixture output
    (spec/local-dev.md L3).
    """
    settings = get_settings()
    return ConfigOut(
        case_types=list(CaseType),
        currencies=list(Currency),
        requested_outcomes=list(RequestedOutcome),
        limits=LimitsOut(
            max_case_files=settings.max_case_files,
            max_case_pages=settings.max_case_pages,
            max_file_bytes=settings.max_file_bytes,
            max_case_bytes=settings.max_case_bytes,
            supported_mime_types=list(settings.supported_mime_types),
        ),
        legal_coverage=LegalCoverage.unvalidated,
        execution_mode=ExecutionMode(settings.ai_mode.value),
    )
