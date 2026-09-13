"""Finding-response schemas (spec/backend.md B7, B9).

A response never resolves a finding: only the next validated assessment decides
its state (B7, frontend.md F4). Disagreement is preserved in history and in the
submitted snapshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.domain.enums import ResponseAction
from app.schemas.common import ResponseModel, StrictModel

#: Bound on a preparer explanation. Long enough for a real justification, short
#: enough to stay a bounded field.
EXPLANATION_MAX_LENGTH = 4_000

#: A response may attach at most the case-wide active-file limit (B4).
MAX_RESPONSE_DOCUMENTS = 10


class FindingResponseIn(StrictModel):
    """``POST /api/findings/{id}/responses`` body (spec/backend.md B9).

    ``document_ids`` must already belong to the case; the response attaches
    existing evidence rather than uploading new bytes (frontend.md F4).
    """

    expected_revision: int
    action: ResponseAction
    explanation: Annotated[str, Field(max_length=EXPLANATION_MAX_LENGTH)] | None = None
    document_ids: Annotated[list[str], Field(max_length=MAX_RESPONSE_DOCUMENTS)] = []


class FindingResponseOut(ResponseModel):
    """A saved preparer response (spec/backend.md B9)."""

    finding_id: str
    action: ResponseAction
    explanation: str | None
    document_ids: list[str]
    created_at: datetime


class FindingResponseResult(ResponseModel):
    """``POST /api/findings/{id}/responses`` response (spec/backend.md B9)."""

    revision: int
    response: FindingResponseOut
