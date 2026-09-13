"""Case and claim routes (spec/backend.md B3, B9).

Covers ``GET/POST /api/cases``, ``GET /api/cases/{id}``,
``PATCH /api/cases/{id}/claim`` and ``POST /api/cases/{id}/intake-check``.

Two invariants shape every handler here:

* Strict, deterministic validation runs before anything expensive, and an
  unsupported case type is rejected with no fallback category and zero model
  calls (B1, B3, BE-01).
* The case ``revision`` is the optimistic-concurrency token. Mutations take a row
  lock, compare ``expected_revision`` and bump it in the same transaction, so a
  stale write is rejected atomically (B9).

The cheap gate result is cached on the claim revision it was computed for, so an
unchanged claim revision reuses it instead of re-evaluating (B3).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.access import (
    active_documents,
    current_claim_revision,
    load_owned_case,
    require_matching_revision,
)
from app.api.deps import CsrfDep, DbDep, PreparerDep
from app.api.views import (
    analysis_out,
    claim_out,
    documents_out,
    finding_response_out,
    intake_out,
    job_out,
)
from app.domain.enums import ClaimOrigin, DocumentState, IntakeStatus, JobKind
from app.intake import GATE_VERSION, GateResult, evaluate_gate
from app.models.analysis import Analysis
from app.models.base import utcnow
from app.models.case import Case, ClaimRevision
from app.models.document import Document
from app.models.finding import Finding, FindingResponse
from app.models.job import Job
from app.models.submission import ReviewEvent, Submission
from app.models.user import User
from app.errors import UNSUPPORTED_CASE_TYPE, ApiError, FieldError
from app.ids import CASE_PREFIX, new_id
from app.money import parse_claim_amount
from app.schemas.cases import (
    ActivityEventOut,
    CaseDetailOut,
    CaseSummaryOut,
    ClaimIn,
    CreateCaseOut,
    IntakeOut,
    PatchClaimIn,
    PatchClaimOut,
    RevisionIn,
)
from app.schemas.common import ListResponse, decimal_to_string
from app.schemas.submissions import SubmissionSummaryOut

logger = logging.getLogger("app.api.cases")

router = APIRouter(tags=["cases"])

#: Cap on activity entries returned with a case, newest first.
ACTIVITY_LIMIT = 50


def _claim_json(claim: ClaimIn) -> dict[str, object]:
    """Return the canonical claim object stored verbatim on the revision.

    Keeping the exact echoed object means an export or submission can reproduce
    what the preparer asserted without re-deriving it from typed columns (B8).
    Amounts stay strings here; they are never JSON floats (B3).
    """
    return {
        "case_type": claim.case_type.value,
        "claimant_name": claim.claimant_name,
        "counterparty_name": claim.counterparty_name,
        "claimed_amount": decimal_to_string(parse_claim_amount(claim.claimed_amount)),
        "currency": claim.currency.value,
        "dates": {
            "contract": claim.dates.contract.isoformat() if claim.dates.contract else None,
            "delivery": claim.dates.delivery.isoformat() if claim.dates.delivery else None,
            "invoice": claim.dates.invoice.isoformat() if claim.dates.invoice else None,
            "payment_due": (
                claim.dates.payment_due.isoformat() if claim.dates.payment_due else None
            ),
        },
        "requested_outcome": claim.requested_outcome.value,
        "narrative": claim.narrative,
        "follow_up_answers": [
            {"question_id": answer.question_id, "answer": answer.answer}
            for answer in claim.follow_up_answers
        ],
    }


def _run_gate(claim: ClaimIn) -> GateResult:
    """Evaluate the cheap gate for ``claim`` (spec/backend.md B3). No model call."""
    return evaluate_gate(
        narrative=claim.narrative,
        claimed_amount=claim.claimed_amount,
        invoice_date_known=claim.dates.invoice is not None,
        follow_up_answers=[
            {"question_id": answer.question_id, "answer": answer.answer}
            for answer in claim.follow_up_answers
        ],
    )


def _write_claim_revision(
    db: DbDep, case: Case, claim: ClaimIn, revision: int, user: User, gate: GateResult
) -> ClaimRevision:
    """Persist one immutable claim revision with its cached gate result (B3, B8).

    ``origin=user_claim``: typed claim data is an assertion by the preparer, not a
    document-derived fact, and never receives document/page provenance (B3).
    """
    row = ClaimRevision(
        case_id=case.id,
        revision=revision,
        case_type=claim.case_type,
        claimant_name=claim.claimant_name,
        counterparty_name=claim.counterparty_name,
        claimed_amount=parse_claim_amount(claim.claimed_amount),
        currency=claim.currency,
        requested_outcome=claim.requested_outcome,
        narrative=claim.narrative,
        date_contract=claim.dates.contract,
        date_delivery=claim.dates.delivery,
        date_invoice=claim.dates.invoice,
        date_payment_due=claim.dates.payment_due,
        follow_up_answers=[
            {"question_id": answer.question_id, "answer": answer.answer}
            for answer in claim.follow_up_answers
        ],
        claim_json=_claim_json(claim),
        origin=ClaimOrigin.user_claim,
        intake_status=gate.status,
        intake_questions=[question.as_dict() for question in gate.questions],
        intake_checked_at=utcnow(),
        intake_gate_version=GATE_VERSION,
        created_by=user.id,
    )
    db.add(row)
    case.intake_status = gate.status
    db.flush()
    return row


@router.get("/cases", response_model=ListResponse[CaseSummaryOut], summary="List your cases")
def list_cases(user: PreparerDep, db: DbDep) -> ListResponse[CaseSummaryOut]:
    """``GET /api/cases`` (spec/backend.md B9): only the signed-in owner's cases.

    Ownership is filtered in SQL rather than checked after loading, so another
    preparer's case can never appear even transiently.
    """
    cases = list(
        db.scalars(
            select(Case).where(Case.owner_id == user.id).order_by(Case.updated_at.desc())
        ).all()
    )
    items: list[CaseSummaryOut] = []
    for case in cases:
        revision = current_claim_revision(db, case)
        items.append(
            CaseSummaryOut(
                case_id=case.id,
                case_type=case.case_type,
                claimant_name=revision.claimant_name,
                counterparty_name=revision.counterparty_name,
                claimed_amount=decimal_to_string(revision.claimed_amount),
                currency=revision.currency,
                revision=case.revision,
                intake_status=case.intake_status,
                updated_at=case.updated_at,
            )
        )
    return ListResponse[CaseSummaryOut](items=items, next_cursor=None)


@router.post(
    "/cases",
    response_model=CreateCaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a case from a structured claim",
)
def create_case(payload: ClaimIn, user: PreparerDep, db: DbDep, _csrf: CsrfDep) -> CreateCaseOut:
    """``POST /api/cases`` (spec/backend.md B9).

    The claim arrives as the direct object (not nested), is validated strictly and
    is stored as revision 1 together with its cheap-gate result. A
    ``needs_information`` gate still creates the case: a valid draft must be
    saveable so uploaded files and typed text are never discarded (B3, FE-02).
    """
    gate = _run_gate(payload)
    case = Case(
        id=new_id(CASE_PREFIX),
        owner_id=user.id,
        case_type=payload.case_type,
        revision=1,
        intake_status=gate.status,
        reference_label=payload.counterparty_name,
    )
    db.add(case)
    db.flush()
    revision = _write_claim_revision(db, case, payload, 1, user, gate)
    logger.info("Case created: case=%s intake=%s", case.id, gate.status.value)
    return CreateCaseOut(case_id=case.id, revision=case.revision, intake=intake_out(revision))


@router.patch(
    "/cases/{case_id}/claim",
    response_model=PatchClaimOut,
    summary="Replace the structured claim with a new revision",
)
def update_claim(
    case_id: str, payload: PatchClaimIn, user: PreparerDep, db: DbDep, _csrf: CsrfDep
) -> PatchClaimOut:
    """``PATCH /api/cases/{id}/claim`` (spec/backend.md B9).

    Writes a *new* claim revision rather than editing the previous one, so a
    submitted snapshot keeps referring to the exact claim it froze (B10). The
    gate is re-evaluated because the claim changed.

    The case type cannot be switched on an existing case: the checklist/legal
    pack is selected by the confirmed case type, and silently repointing it would
    invalidate every existing finding's basis (B5).
    """
    case = load_owned_case(db, case_id, user, lock=True)
    require_matching_revision(case, payload.expected_revision)

    if payload.claim.case_type != case.case_type:
        raise ApiError(
            UNSUPPORTED_CASE_TYPE,
            "The case type cannot be changed on an existing case.",
            field_errors=[
                FieldError("case_type", "This case was created with a different case type.")
            ],
        )

    gate = _run_gate(payload.claim)
    new_revision = case.revision + 1
    case.revision = new_revision
    row = _write_claim_revision(db, case, payload.claim, new_revision, user, gate)
    return PatchClaimOut(
        revision=new_revision, intake=intake_out(row), claim=claim_out(row)
    )


@router.post(
    "/cases/{case_id}/intake-check",
    response_model=IntakeOut,
    summary="Run the cheap intake gate for the current claim revision",
)
def check_intake(
    case_id: str, payload: RevisionIn, user: PreparerDep, db: DbDep, _csrf: CsrfDep
) -> IntakeOut:
    """``POST /api/cases/{id}/intake-check`` (spec/backend.md B3, B9).

    Makes no provider call. The result is cached on the claim revision, so
    re-running it for an unchanged revision returns the stored answer instead of
    re-evaluating (B3). Because the gate is a pure function of the stored claim,
    "cached" and "recomputed" are indistinguishable to the client; the cache
    exists to keep this route cheap, not to hide staleness.
    """
    case = load_owned_case(db, case_id, user)
    require_matching_revision(case, payload.expected_revision)
    revision = current_claim_revision(db, case)

    if (
        revision.intake_status is not IntakeStatus.not_checked
        and revision.intake_gate_version == GATE_VERSION
    ):
        return intake_out(revision)

    gate = evaluate_gate(
        narrative=revision.narrative,
        claimed_amount=decimal_to_string(revision.claimed_amount),
        invoice_date_known=revision.date_invoice is not None,
        follow_up_answers=list(revision.follow_up_answers),
    )
    revision.intake_status = gate.status
    revision.intake_questions = [question.as_dict() for question in gate.questions]
    revision.intake_checked_at = utcnow()
    revision.intake_gate_version = GATE_VERSION
    case.intake_status = gate.status
    db.flush()
    return intake_out(revision)


def _activity(db: DbDep, case: Case) -> list[ActivityEventOut]:
    """Derive the case activity log from durable rows (spec/backend.md B9).

    There is no separate audit table: every entry is read back from the row that
    actually recorded the event, so the log cannot claim something the data does
    not support. Reviewer clarification requests are included because the
    preparer must see them in their case activity (frontend.md F4).
    """
    entries: list[ActivityEventOut] = []

    for revision in db.scalars(
        select(ClaimRevision)
        .where(ClaimRevision.case_id == case.id)
        .order_by(ClaimRevision.revision)
    ).all():
        entries.append(
            ActivityEventOut(
                id=f"claim-{case.id}-{revision.revision}",
                type="claim_created" if revision.revision == 1 else "claim_updated",
                message=(
                    "Dossier créé."
                    if revision.revision == 1
                    else f"Réclamation mise à jour (révision {revision.revision})."
                ),
                created_at=revision.created_at,
            )
        )

    for document in db.scalars(
        select(Document).where(Document.case_id == case.id).order_by(Document.created_at)
    ).all():
        if document.state is DocumentState.rejected:
            message = f"Fichier refusé : {document.display_name}."
            kind = "document_rejected"
        else:
            message = f"Document ajouté : {document.display_name}."
            kind = "document_added"
        entries.append(
            ActivityEventOut(
                id=f"doc-{document.id}",
                type=kind,
                message=message,
                created_at=document.created_at,
            )
        )
        if document.detached_at is not None:
            entries.append(
                ActivityEventOut(
                    id=f"doc-detach-{document.id}",
                    type="document_removed",
                    message=f"Document retiré : {document.display_name}.",
                    created_at=document.detached_at,
                )
            )

    for analysis in db.scalars(
        select(Analysis).where(Analysis.case_id == case.id).order_by(Analysis.created_at)
    ).all():
        entries.append(
            ActivityEventOut(
                id=f"run-{analysis.id}",
                type="analysis_published",
                message=(
                    f"Analyse publiée pour la révision {analysis.revision} "
                    f"(statut : {analysis.status.value})."
                ),
                created_at=analysis.published_at or analysis.created_at,
            )
        )

    for response in db.scalars(
        select(FindingResponse)
        .where(FindingResponse.case_id == case.id)
        .order_by(FindingResponse.created_at)
    ).all():
        entries.append(
            ActivityEventOut(
                id=f"resp-{response.id}",
                type="finding_response",
                message=f"Réponse enregistrée : {response.action.value}.",
                created_at=response.created_at,
            )
        )

    submissions = list(
        db.scalars(
            select(Submission)
            .where(Submission.case_id == case.id)
            .order_by(Submission.submitted_at)
        ).all()
    )
    for submission in submissions:
        entries.append(
            ActivityEventOut(
                id=f"sub-{submission.id}",
                type="submission_sent",
                message=(
                    f"Dossier transmis pour examen sur la plateforme "
                    f"(révision {submission.revision})."
                ),
                created_at=submission.submitted_at,
            )
        )

    if submissions:
        submission_ids = [submission.id for submission in submissions]
        for event in db.scalars(
            select(ReviewEvent)
            .where(ReviewEvent.submission_id.in_(submission_ids))
            .order_by(ReviewEvent.created_at)
        ).all():
            entries.append(
                ActivityEventOut(
                    id=f"evt-{event.id}",
                    type=f"review_{event.event_type.value}",
                    message=event.message or f"Examen : {event.event_type.value}.",
                    created_at=event.created_at,
                )
            )

    entries.sort(key=lambda entry: entry.created_at, reverse=True)
    return entries[:ACTIVITY_LIMIT]


@router.get("/cases/{case_id}", response_model=CaseDetailOut, summary="Read one case")
def get_case(case_id: str, user: PreparerDep, db: DbDep) -> CaseDetailOut:
    """``GET /api/cases/{id}`` (spec/backend.md B9).

    Returns the working case: current claim and revision, documents, the most
    recent job and published analysis, submission summaries, the activity log and
    every saved preparer response.

    ``latest_analysis`` is the most recently published run for this case even when
    the case has moved on since; its ``revision`` field is what tells the UI the
    result is stale, so the staleness is visible instead of being hidden by
    withholding the run (B7, FE-04).
    """
    case = load_owned_case(db, case_id, user)
    revision = current_claim_revision(db, case)

    latest_job = db.scalar(
        select(Job)
        .where(Job.case_id == case.id, Job.kind == JobKind.analysis)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    latest_analysis = db.scalar(
        select(Analysis).where(Analysis.case_id == case.id).order_by(Analysis.created_at.desc()).limit(1)
    )

    submissions = [
        SubmissionSummaryOut(
            submission_id=submission.id,
            revision=submission.revision,
            recipient_id=submission.recipient_id,
            status=submission.state,
            submitted_at=submission.submitted_at,
        )
        for submission in db.scalars(
            select(Submission)
            .where(Submission.case_id == case.id)
            .order_by(Submission.submitted_at.desc())
        ).all()
    ]

    responses = [
        finding_response_out(response)
        for response in db.scalars(
            select(FindingResponse)
            .join(Finding, Finding.id == FindingResponse.finding_id)
            .where(FindingResponse.case_id == case.id)
            .order_by(FindingResponse.created_at)
        ).all()
    ]

    return CaseDetailOut(
        case_id=case.id,
        revision=case.revision,
        claim=claim_out(revision),
        intake=intake_out(revision),
        documents=documents_out(db, active_documents(db, case.id)),
        latest_job=job_out(latest_job) if latest_job is not None else None,
        latest_analysis=(
            analysis_out(db, latest_analysis) if latest_analysis is not None else None
        ),
        submissions=submissions,
        activity=_activity(db, case),
        responses=responses,
    )
