"""Recipient, export, submission and review-event schemas (B9, B10).

Submission targets are server-owned rows, so a preparer cannot submit to an
arbitrary address (B9). A submission freezes the claim revision, document
hashes, checklist version, published run, preparer responses, recipient and
timestamp; received/reviewed states record reviewer activity only and never
indicate legal acceptance (B10).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.domain.enums import ExportState, ReviewEventType, SubmissionState
from app.schemas.common import ResponseModel, StrictModel

#: Bound on a reviewer clarification message.
REVIEW_MESSAGE_MAX_LENGTH = 4_000


class RecipientOut(ResponseModel):
    """One authorized reviewer destination (spec/backend.md B9, B10).

    ``remit`` is descriptive only: it must not claim official filing, legal
    acceptance or certification.
    """

    recipient_id: str
    name: str
    remit: str


class ExportIn(StrictModel):
    """``POST /api/cases/{id}/exports`` body (spec/backend.md B9, B10).

    ``acknowledge_unresolved`` is required to package a ``partial`` analysis or
    one with open findings; the limitations are always included either way.
    """

    expected_revision: int
    analysis_id: str
    acknowledge_unresolved: bool = False


class StartExportOut(ResponseModel):
    """``POST /api/cases/{id}/exports`` response: 202 accepted (B9)."""

    job_id: str
    export_id: str


class ExportOut(ResponseModel):
    """Export package state (spec/backend.md B10, frontend.md F4)."""

    export_id: str
    status: ExportState


class SubmissionIn(StrictModel):
    """``POST /api/cases/{id}/submissions`` body (spec/backend.md B9, B10)."""

    expected_revision: int
    analysis_id: str
    recipient_id: str
    acknowledge_unresolved: bool = False


class SubmissionOut(ResponseModel):
    """``POST /api/cases/{id}/submissions`` response: 201 (spec/backend.md B9)."""

    submission_id: str
    case_id: str
    revision: int
    analysis_id: str
    recipient_id: str
    status: SubmissionState
    submitted_at: datetime


class SubmissionSummaryOut(ResponseModel):
    """Submission summary inside ``GET /api/cases/{id}`` (spec/backend.md B9)."""

    submission_id: str
    revision: int
    recipient_id: str
    status: SubmissionState
    submitted_at: datetime


class ReviewerSubmissionSummaryOut(ResponseModel):
    """One row of ``GET /api/reviewer/submissions`` (spec/backend.md B9).

    Only submissions assigned to the signed-in reviewer are listed; access to one
    submission grants nothing else (B10).
    """

    submission_id: str
    case_id: str
    claimant_name: str
    revision: int
    status: SubmissionState
    submitted_at: datetime


class ReviewEventIn(StrictModel):
    """``POST /api/reviewer/submissions/{id}/events`` body (spec/backend.md B9)."""

    event_type: ReviewEventType
    message: Annotated[str, Field(max_length=REVIEW_MESSAGE_MAX_LENGTH)] | None = None


class ReviewEventOut(ResponseModel):
    """A recorded reviewer action (spec/backend.md B9, B10)."""

    event_id: str
    event_type: ReviewEventType
    message: str | None
    created_at: datetime
