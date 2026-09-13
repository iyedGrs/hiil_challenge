"""Case, claim and intake schemas (spec/backend.md B3, B9).

Request models forbid extra fields and validate types explicitly rather than
relying on coercion (B3): ``claimed_amount`` must arrive as a canonical decimal
*string*, and every date key must be present with ``null`` meaning "not known".

The narrative is data, never instructions (B3, B15). Nothing in this module
interprets it; it is length-checked and stored.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import Field, field_validator

from app.domain.enums import (
    CaseType,
    Currency,
    IntakeStatus,
    RequestedOutcome,
)
from app.money import AmountFormatError, parse_claim_amount
from app.schemas.analyses import AnalysisOut
from app.schemas.common import ResponseModel, StrictModel
from app.schemas.documents import DocumentOut
from app.schemas.findings import FindingResponseOut
from app.schemas.jobs import JobOut
from app.schemas.readiness import ReadinessOut
from app.schemas.submissions import SubmissionSummaryOut

#: Bounds from the B3 input-constraints table.
NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 200
NARRATIVE_MIN_LENGTH = 30
NARRATIVE_MAX_LENGTH = 4_000
MAX_FOLLOW_UP_ANSWERS = 5
FOLLOW_UP_ANSWER_MAX_LENGTH = 1_000


class DatesIn(StrictModel):
    """The four explicit claim date keys (spec/backend.md B3, B9).

    Every key is required so an unknown date is recorded as an explicit ``null``
    rather than being silently absent -- and never fabricated.
    """

    contract: date | None
    delivery: date | None
    invoice: date | None
    payment_due: date | None


class FollowUpAnswerIn(StrictModel):
    """One answer to a server-issued intake question (spec/backend.md B3)."""

    question_id: Annotated[str, Field(min_length=1, max_length=100)]
    answer: Annotated[str, Field(min_length=1, max_length=FOLLOW_UP_ANSWER_MAX_LENGTH)]


class ClaimIn(StrictModel):
    """The canonical structured claim (spec/backend.md B3, B9).

    ``case_type``, ``currency`` and ``requested_outcome`` are exact enums, so an
    unsupported category is rejected here -- before any model call and with no
    fallback to a default category (B1, B3).
    """

    case_type: CaseType
    claimant_name: str
    counterparty_name: str
    #: Canonical decimal string. A JSON float is a type error, not a value to
    #: coerce (B3).
    claimed_amount: str
    currency: Currency
    dates: DatesIn
    requested_outcome: RequestedOutcome
    narrative: str
    follow_up_answers: Annotated[
        list[FollowUpAnswerIn], Field(max_length=MAX_FOLLOW_UP_ANSWERS)
    ] = []

    @field_validator("claimant_name", "counterparty_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not (NAME_MIN_LENGTH <= len(trimmed) <= NAME_MAX_LENGTH):
            raise ValueError(
                f"Must contain between {NAME_MIN_LENGTH} and {NAME_MAX_LENGTH} characters."
            )
        return trimmed

    @field_validator("narrative")
    @classmethod
    def _check_narrative(cls, value: str) -> str:
        trimmed = value.strip()
        if not (NARRATIVE_MIN_LENGTH <= len(trimmed) <= NARRATIVE_MAX_LENGTH):
            raise ValueError(
                f"Must contain between {NARRATIVE_MIN_LENGTH} and "
                f"{NARRATIVE_MAX_LENGTH} characters."
            )
        return trimmed

    @field_validator("claimed_amount")
    @classmethod
    def _check_amount(cls, value: str) -> str:
        try:
            parse_claim_amount(value)
        except AmountFormatError as exc:
            raise ValueError(str(exc)) from None
        return value.strip()

    @field_validator("follow_up_answers")
    @classmethod
    def _unique_question_ids(cls, value: list[FollowUpAnswerIn]) -> list[FollowUpAnswerIn]:
        seen = {answer.question_id for answer in value}
        if len(seen) != len(value):
            raise ValueError("Each question may be answered at most once.")
        return value


class PatchClaimIn(StrictModel):
    """``PATCH /api/cases/{id}/claim`` body (spec/backend.md B9)."""

    expected_revision: int
    claim: ClaimIn


class RevisionIn(StrictModel):
    """Body carrying only an optimistic-concurrency token (B9).

    Used by ``POST /api/cases/{id}/intake-check`` and
    ``POST /api/cases/{id}/analyses``.
    """

    expected_revision: int


# --- Responses ---------------------------------------------------------------


class DatesOut(ResponseModel):
    """Claim dates as ISO dates or null (spec/backend.md B9)."""

    contract: date | None
    delivery: date | None
    invoice: date | None
    payment_due: date | None


class FollowUpAnswerOut(ResponseModel):
    """A stored answer echoed back with the claim (spec/backend.md B3)."""

    question_id: str
    answer: str


class ClaimOut(ResponseModel):
    """The stored claim echoed back; amounts are decimal strings (B9)."""

    case_type: CaseType
    claimant_name: str
    counterparty_name: str
    claimed_amount: str
    currency: Currency
    dates: DatesOut
    requested_outcome: RequestedOutcome
    narrative: str
    follow_up_answers: list[FollowUpAnswerOut]


class IntakeQuestionOut(ResponseModel):
    """One targeted, stable intake question (spec/backend.md B3, B9).

    ``field`` names the claim input the question is about, so the UI can render
    it next to that input instead of as a generic failure.
    """

    id: str
    field: str
    message: str


class IntakeOut(ResponseModel):
    """``{status, questions}`` (spec/backend.md B9).

    ``ready`` means enough information exists to attempt the supported document
    checks. It is not a decision on the merits (B3).
    """

    status: IntakeStatus
    questions: list[IntakeQuestionOut]


class CreateCaseOut(ResponseModel):
    """``POST /api/cases`` response: ``{case_id, revision, intake}`` (B9)."""

    case_id: str
    revision: int
    intake: IntakeOut


class PatchClaimOut(ResponseModel):
    """``PATCH /api/cases/{id}/claim`` response (spec/backend.md B9)."""

    revision: int
    intake: IntakeOut
    claim: ClaimOut


class CaseSummaryOut(ResponseModel):
    """One row of ``GET /api/cases`` (spec/backend.md B9)."""

    case_id: str
    case_type: CaseType
    claimant_name: str
    counterparty_name: str
    claimed_amount: str
    currency: Currency
    revision: int
    intake_status: IntakeStatus
    updated_at: datetime


class ActivityEventOut(ResponseModel):
    """One entry in the case activity log (spec/backend.md B9).

    Derived from the durable rows that already record what happened (documents,
    analyses, responses, submissions, reviewer events) rather than from a
    separate free-text audit table, so the log cannot drift from the facts.
    """

    id: str
    type: str
    message: str
    created_at: datetime


class CaseDetailOut(ResponseModel):
    """``GET /api/cases/{id}`` (spec/backend.md B9).

    Composite view: the current claim and revision, the working set of
    documents, the latest job/analysis, submission summaries, the activity log
    and every preparer response saved for this case's findings.
    """

    case_id: str
    revision: int
    claim: ClaimOut
    intake: IntakeOut
    documents: list[DocumentOut]
    latest_job: JobOut | None
    latest_analysis: AnalysisOut | None
    readiness: ReadinessOut
    submissions: list[SubmissionSummaryOut]
    activity: list[ActivityEventOut]
    responses: list[FindingResponseOut]
