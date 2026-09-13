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
    """Ingestion limits enforced before any provider call (spec/backend.md B4).

    Field names are the ones the UI consumes (``frontend/src/api/types.ts``
    ``ConfigLimits``): ``max_active_files``/``max_total_pages`` describe the
    limit as the preparer experiences it (active files, total pages in the
    case), while the server-side settings that back them are named
    ``MAX_CASE_FILES``/``MAX_CASE_PAGES`` in the L3 environment contract.
    """

    max_active_files: int
    max_total_pages: int
    max_file_bytes: int
    max_case_bytes: int
    supported_mime_types: list[str]


class ConfigOut(ResponseModel):
    """``{case_types, currencies, requested_outcomes, limits, legal_coverage,
    execution_mode}`` (spec/backend.md B9).

    ``legal_coverage`` is a map from case type to its coverage status rather
    than a single value: the backend maps each confirmed case type to its own
    pack version (B5), so coverage is per case type even though today only one
    category exists. This matches the UI's ``ConfigLegalCoverage``.
    """

    case_types: list[CaseType]
    currencies: list[Currency]
    requested_outcomes: list[RequestedOutcome]
    limits: LimitsOut
    legal_coverage: dict[str, LegalCoverage]
    execution_mode: ExecutionMode
