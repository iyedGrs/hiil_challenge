"""``GET /api/config`` (spec/backend.md B9).

Publishes the enumerated vocabulary, ingestion limits, current legal coverage and
execution mode. No authentication is required: the UI needs this before a session
exists, and nothing here is case data or a secret.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbDep
from app.config import get_settings
from app.domain.enums import (
    CaseType,
    Currency,
    ExecutionMode,
    LegalCoverage,
    RequestedOutcome,
)
from app.models.legal import LegalPack
from app.schemas.config import ConfigOut, LimitsOut

logger = logging.getLogger("app.api.config")

router = APIRouter(tags=["config"])


def _current_legal_coverage(db: DbDep) -> dict[str, LegalCoverage]:
    """Return per-case-type coverage of the configured legal pack (B5).

    Queries ``legal_packs`` for ``settings.legal_pack_version`` instead of a
    hardcoded literal, so a future reviewed pack automatically flips a case type
    to ``validated`` without a code change. Every supported case type is always
    present in the map and defaults to ``unvalidated``.

    Any lookup failure -- no pack loaded yet, table not migrated, or a
    stale/unreachable connection -- falls back to ``unvalidated`` rather than
    raising: B5 requires disabling claims of legal-requirement verification
    whenever a validated pack is unavailable, and ``GET /config`` must never 500
    because of it.
    """
    settings = get_settings()
    coverage: dict[str, LegalCoverage] = {
        case_type.value: LegalCoverage.unvalidated for case_type in CaseType
    }
    try:
        pack = db.get(LegalPack, settings.legal_pack_version)
    except SQLAlchemyError:
        logger.warning(
            "Legal pack lookup failed for version=%s; reporting unvalidated.",
            settings.legal_pack_version,
            exc_info=True,
        )
        return coverage
    if pack is not None:
        coverage[pack.case_type.value] = pack.coverage
    return coverage


@router.get("/config", response_model=ConfigOut, summary="Client bootstrap configuration")
def read_config(db: DbDep) -> ConfigOut:
    """Return the contract vocabulary and limits (spec/backend.md B9).

    ``legal_coverage`` reflects the actually-loaded pack for
    ``settings.legal_pack_version`` (B5). In this hackathon demo the shipped
    pack is unreviewed, so this still resolves to ``unvalidated`` in practice --
    but through the real lookup, not a hardcoded literal.

    ``execution_mode`` mirrors ``AI_MODE`` so the UI can label fixture output
    (spec/local-dev.md L3).
    """
    settings = get_settings()
    return ConfigOut(
        case_types=list(CaseType),
        currencies=list(Currency),
        requested_outcomes=list(RequestedOutcome),
        limits=LimitsOut(
            max_active_files=settings.max_case_files,
            max_total_pages=settings.max_case_pages,
            max_file_bytes=settings.max_file_bytes,
            max_case_bytes=settings.max_case_bytes,
            supported_mime_types=list(settings.supported_mime_types),
        ),
        legal_coverage=_current_legal_coverage(db),
        execution_mode=ExecutionMode(settings.ai_mode.value),
    )
