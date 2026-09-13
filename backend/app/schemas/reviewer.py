"""Reviewer snapshot schema (spec/backend.md B9, B10).

Lives in its own module because it composes the claim, document, analysis,
response and event shapes; keeping it out of ``schemas/cases.py`` avoids a
circular import between the case and submission schema modules.

Everything here is a frozen copy taken at submission time. Detaching a file or
editing the working case afterwards cannot change what the reviewer received
(B10).
"""

from __future__ import annotations

from app.schemas.analyses import AnalysisOut
from app.schemas.cases import ClaimOut
from app.schemas.common import ResponseModel
from app.schemas.documents import DocumentOut
from app.schemas.findings import FindingResponseOut
from app.schemas.readiness import ReadinessOut
from app.schemas.submissions import ReviewEventOut


class ReviewerSubmissionDetailOut(ResponseModel):
    """``GET /api/reviewer/submissions/{id}`` (spec/backend.md B9, B10)."""

    submission_id: str
    case_id: str
    revision: int
    claim: ClaimOut
    documents: list[DocumentOut]
    analysis: AnalysisOut
    readiness: ReadinessOut
    responses: list[FindingResponseOut]
    events: list[ReviewEventOut]
