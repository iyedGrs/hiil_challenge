"""``GET /api/config`` schema (spec/backend.md B9).

Advertises the enumerated vocabulary and ingestion limits the UI needs before a
session exists, plus the current legal coverage and execution mode so the client
can render the required disclosure labels (B5, B10).
"""

from __future__ import annotations

from app.domain.enums import (
    CaseType,
    Currency,
    ExecutionMode,
    LegalCoverage,
    RequestedOutcome,
)
from app.schemas.common import ResponseModel


class LimitsOut(ResponseModel):
    """Ingestion limits enforced before any provider call (spec/backend.md B4)."""

    max_case_files: int
    max_case_pages: int
    max_file_bytes: int
    max_case_bytes: int
    supported_mime_types: list[str]


class ConfigOut(ResponseModel):
    """``{case_types, currencies, requested_outcomes, limits, legal_coverage,
    execution_mode}`` (spec/backend.md B9).
    """

    case_types: list[CaseType]
    currencies: list[Currency]
    requested_outcomes: list[RequestedOutcome]
    limits: LimitsOut
    legal_coverage: LegalCoverage
    execution_mode: ExecutionMode
