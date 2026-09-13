"""Job schemas (spec/backend.md B8, B9).

``GET /api/jobs/{id}`` is the only progress surface. Phase and both result IDs
are nullable by contract, and ``error`` carries the sanitized stored message
only -- never a traceback, provider payload or document content (B9, L6).
"""

from __future__ import annotations

from app.domain.enums import JobPhase, JobStatus
from app.schemas.common import ResponseModel


class JobOut(ResponseModel):
    """``{id, status, phase, error, result_analysis_id, result_export_id}`` (B9)."""

    id: str
    status: JobStatus
    phase: JobPhase | None
    error: str | None
    result_analysis_id: str | None
    result_export_id: str | None


class StartAnalysisOut(ResponseModel):
    """``POST /api/cases/{id}/analyses`` response: 202 accepted (B9)."""

    job_id: str
    case_id: str
    revision: int
