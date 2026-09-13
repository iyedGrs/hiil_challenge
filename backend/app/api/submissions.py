"""Recipients, exports, submissions and the reviewer back office (B9, B10).

The handoff rules this module enforces:

* An **assessed** package or submission requires a *current published* analysis.
  A run for an older revision answers 409 ``ANALYSIS_OUTDATED``; an unpublished one
  answers 409 ``ANALYSIS_NOT_PUBLISHED``. A failed or unvalidated run can never be
  presented as an assessed dossier (B10).
* ``partial`` coverage or open findings are allowed **only** with explicit
  ``acknowledge_unresolved``, and the limitations ship either way (B10).
* Recipients are server-owned rows, so a preparer cannot submit to an arbitrary
  address (B9).
* A submission **freezes** the claim revision, document hashes, checklist version,
  published run, preparer responses, recipient and timestamp. Detaching a file
  afterwards cannot change what the reviewer received (B10).
* Explicit submission is the only path to reviewer access, and access to one
  submission grants nothing else (B10).

Received/reviewed states record reviewer activity only. They never indicate legal
acceptance, and no route here implies an official filing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select

from app.api.access import current_claim_revision, load_owned_case, require_matching_revision
from app.api.deps import CsrfDep, DbDep, PreparerDep, ReviewerDep
from app.api.idempotency import (
    SCOPE_EXPORT,
    SCOPE_SUBMISSION,
    fingerprint,
    idempotency_key_header,
    reuse_or_claim,
)
from app.api.views import analysis_out
from app.config import get_settings
from app.domain.enums import (
    AnalysisStatus,
    DocumentState,
    ExportState,
    FindingStatus,
    JobKind,
    JobStatus,
    ReviewEventType,
    SubmissionState,
)
from app.errors import (
    ANALYSIS_NOT_PUBLISHED,
    ANALYSIS_OUTDATED,
    EXPORT_NOT_READY,
    INVALID_INPUT,
    ApiError,
    FieldError,
    not_found,
)
from app.files import read_bytes
from app.ids import EVENT_PREFIX, EXPORT_PREFIX, JOB_PREFIX, SUBMISSION_PREFIX, new_id
from app.models.analysis import Analysis, CheckResultRow
from app.models.base import utcnow
from app.models.case import Case
from app.models.document import Document
from app.models.finding import Finding, FindingResponse
from app.models.job import Job
from app.models.submission import Export, ReviewEvent, Submission, SubmissionDocument
from app.models.user import Recipient, User
from app.schemas.cases import ClaimOut, DatesOut, FollowUpAnswerOut
from app.schemas.common import ListResponse
from app.schemas.documents import DocumentOut
from app.schemas.reviewer import ReviewerSubmissionDetailOut
from app.schemas.submissions import (
    ExportIn,
    RecipientOut,
    ReviewEventIn,
    ReviewEventOut,
    ReviewerSubmissionSummaryOut,
    StartExportOut,
    SubmissionIn,
    SubmissionOut,
)

logger = logging.getLogger("app.api.submissions")

router = APIRouter(tags=["handoff"])


def _load_current_published_analysis(
    db: DbDep, case: Case, analysis_id: str
) -> Analysis:
    """Return the analysis if it is published and current for ``case`` (B10).

    Raises:
        ApiError: 404 when it does not belong to the case, 409
            ``ANALYSIS_NOT_PUBLISHED`` while it is still running, 409
            ``ANALYSIS_OUTDATED`` when the case has moved past it.
    """
    analysis = db.scalar(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.case_id == case.id)
    )
    if analysis is None:
        raise not_found()
    if analysis.published_at is None:
        raise ApiError(
            ANALYSIS_NOT_PUBLISHED, "This assessment has not finished publishing yet."
        )
    if analysis.revision != case.revision:
        raise ApiError(
            ANALYSIS_OUTDATED,
            "The case changed after this assessment. Reassess before sharing it.",
        )
    return analysis


def _require_acknowledgement(
    db: DbDep, analysis: Analysis, acknowledge_unresolved: bool
) -> int:
    """Count open findings and require acknowledgement when there are any (B10).

    A ``partial`` analysis needs the same acknowledgement: incomplete coverage is
    itself an unresolved state, and shipping it silently would present a limited
    review as a complete one.
    """
    open_findings = int(
        db.scalar(
            select(func.count())
            .select_from(CheckResultRow)
            .where(
                CheckResultRow.analysis_id == analysis.id,
                CheckResultRow.finding_status == FindingStatus.open,
            )
        )
        or 0
    )
    needs_acknowledgement = open_findings > 0 or analysis.status is AnalysisStatus.partial
    if needs_acknowledgement and not acknowledge_unresolved:
        raise ApiError(
            INVALID_INPUT,
            "This assessment has unresolved items or partial coverage. "
            "Acknowledge them explicitly to continue.",
            field_errors=[
                FieldError(
                    "acknowledge_unresolved",
                    "Confirm that you are sharing a dossier with unresolved items.",
                )
            ],
        )
    return open_findings


@router.get(
    "/recipients",
    response_model=ListResponse[RecipientOut],
    summary="List authorized reviewer destinations",
)
def list_recipients(user: PreparerDep, db: DbDep) -> ListResponse[RecipientOut]:
    """``GET /api/recipients`` (spec/backend.md B9, B10).

    Server-owned destinations only. There is no arbitrary-email submission path.
    """
    recipients = list(
        db.scalars(
            select(Recipient).where(Recipient.is_active.is_(True)).order_by(Recipient.label)
        ).all()
    )
    return ListResponse[RecipientOut](
        items=[
            RecipientOut(recipient_id=row.id, name=row.label, remit=row.remit)
            for row in recipients
        ],
        next_cursor=None,
    )


@router.post(
    "/cases/{case_id}/exports",
    response_model=StartExportOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate the reviewer package for a published analysis",
)
def create_export(
    case_id: str,
    payload: ExportIn,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
    response: Response,
    idempotency_key: str | None = Depends(idempotency_key_header),
) -> StartExportOut:
    """``POST /api/cases/{id}/exports`` -> 202 ``{job_id, export_id}`` (B9, B10)."""
    case = load_owned_case(db, case_id, user, lock=True)
    require_matching_revision(case, payload.expected_revision)

    request_fingerprint = fingerprint(
        {
            "case_id": case.id,
            "revision": payload.expected_revision,
            "analysis_id": payload.analysis_id,
            "acknowledge_unresolved": payload.acknowledge_unresolved,
        }
    )
    record, is_replay = reuse_or_claim(
        db,
        case_id=case.id,
        scope=SCOPE_EXPORT,
        key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if is_replay and record is not None and record.result_id and record.job_id:
        response.status_code = status.HTTP_200_OK
        return StartExportOut(job_id=record.job_id, export_id=record.result_id)

    analysis = _load_current_published_analysis(db, case, payload.analysis_id)
    _require_acknowledgement(db, analysis, payload.acknowledge_unresolved)

    export = Export(
        id=new_id(EXPORT_PREFIX),
        case_id=case.id,
        analysis_id=analysis.id,
        revision=analysis.revision,
        state=ExportState.generating,
        acknowledge_unresolved=payload.acknowledge_unresolved,
        created_by=user.id,
    )
    db.add(export)
    db.flush()

    job = Job(
        id=new_id(JOB_PREFIX),
        case_id=case.id,
        kind=JobKind.export,
        status=JobStatus.queued,
        idempotency_key=idempotency_key or f"auto-{export.id}",
        input_revision=case.revision,
        payload={"export_id": export.id, "analysis_id": analysis.id},
        requested_by=user.id,
    )
    db.add(job)
    db.flush()
    if record is not None:
        record.job_id = job.id
        record.result_id = export.id

    logger.info("Export queued: case=%s export=%s job=%s", case.id, export.id, job.id)
    return StartExportOut(job_id=job.id, export_id=export.id)


@router.get("/exports/{export_id}/content", summary="Download a completed package")
def get_export_content(export_id: str, user: PreparerDep, db: DbDep) -> Response:
    """``GET /api/exports/{id}/content`` (spec/backend.md B9, B10).

    Answers 409 ``EXPORT_NOT_READY`` while the package is generating or after it
    failed, rather than serving a partial or missing archive.
    """
    settings = get_settings()
    export = db.scalar(
        select(Export)
        .join(Case, Case.id == Export.case_id)
        .where(Export.id == export_id, Case.owner_id == user.id)
    )
    if export is None:
        raise not_found()
    if export.state is not ExportState.ready or export.storage_key is None:
        raise ApiError(
            EXPORT_NOT_READY,
            "The package is not ready yet."
            if export.state is ExportState.generating
            else "The package could not be generated.",
        )
    data = read_bytes(settings.file_storage_root, export.storage_key)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="dossier-{export.id}.zip"'},
    )


@router.post(
    "/cases/{case_id}/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a dossier version to an assigned reviewer",
)
def create_submission(
    case_id: str,
    payload: SubmissionIn,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
    response: Response,
    idempotency_key: str | None = Depends(idempotency_key_header),
) -> SubmissionOut:
    """``POST /api/cases/{id}/submissions`` -> 201 (spec/backend.md B9, B10).

    Freezes everything the reviewer will see in one transaction: the claim
    revision, each document's name/hash/size/storage key, the checklist version,
    the published run, the preparer's responses, the recipient and the timestamp.
    """
    case = load_owned_case(db, case_id, user, lock=True)
    require_matching_revision(case, payload.expected_revision)

    request_fingerprint = fingerprint(
        {
            "case_id": case.id,
            "revision": payload.expected_revision,
            "analysis_id": payload.analysis_id,
            "recipient_id": payload.recipient_id,
            "acknowledge_unresolved": payload.acknowledge_unresolved,
        }
    )
    record, is_replay = reuse_or_claim(
        db,
        case_id=case.id,
        scope=SCOPE_SUBMISSION,
        key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if is_replay and record is not None and record.result_id:
        existing = db.get(Submission, record.result_id)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return _submission_out(existing)

    analysis = _load_current_published_analysis(db, case, payload.analysis_id)
    open_findings = _require_acknowledgement(db, analysis, payload.acknowledge_unresolved)

    recipient = db.scalar(
        select(Recipient).where(
            Recipient.id == payload.recipient_id, Recipient.is_active.is_(True)
        )
    )
    if recipient is None:
        raise ApiError(
            INVALID_INPUT,
            "That reviewer destination is not available.",
            field_errors=[FieldError("recipient_id", "Unknown or inactive destination.")],
        )

    claim = current_claim_revision(db, case)
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case.id, Document.is_active.is_(True))
            .order_by(Document.created_at)
        ).all()
    )
    responses = list(
        db.execute(
            select(Finding, FindingResponse)
            .join(FindingResponse, FindingResponse.finding_id == Finding.id)
            .where(Finding.case_id == case.id)
            .order_by(FindingResponse.created_at)
        ).all()
    )

    submission = Submission(
        id=new_id(SUBMISSION_PREFIX),
        case_id=case.id,
        analysis_id=analysis.id,
        recipient_id=recipient.id,
        reviewer_id=recipient.reviewer_id,
        preparer_id=user.id,
        revision=case.revision,
        checklist_version=analysis.checklist_version,
        state=SubmissionState.submitted,
        acknowledge_unresolved=payload.acknowledge_unresolved,
        claim_snapshot=dict(claim.claim_json),
        response_snapshot=[
            {
                "finding_id": finding.id,
                "check_id": finding.check_id,
                "subject_id": finding.subject_id,
                "action": response_row.action.value,
                "explanation": response_row.explanation,
                "document_ids": list(response_row.document_ids),
                "created_at": response_row.created_at.isoformat(),
            }
            for finding, response_row in responses
        ],
        manifest={
            "analysis_status": analysis.status.value,
            "execution_mode": analysis.execution_mode.value,
            "legal_coverage": analysis.legal_coverage.value,
            "coverage": analysis.coverage,
            "disclosures": analysis.disclosures,
            "unresolved_count": open_findings,
            "claimant_name": claim.claimant_name,
            # Frozen document view, so a later detach cannot change what the
            # reviewer sees (spec/backend.md B10).
            "documents": [
                {
                    "document_id": document.id,
                    "filename": document.display_name,
                    "pages": document.page_count,
                    "size_bytes": document.byte_size,
                    "sha256": document.sha256,
                    "state": document.state.value,
                }
                for document in documents
            ],
        },
    )
    db.add(submission)
    db.flush()

    for index, document in enumerate(documents):
        db.add(
            SubmissionDocument(
                submission_id=submission.id,
                document_id=document.id,
                display_name=document.display_name,
                storage_key=document.storage_key,
                mime_type=document.mime_type,
                byte_size=document.byte_size,
                sha256=document.sha256,
                page_count=document.page_count,
                sort_order=index,
            )
        )

    db.flush()
    if record is not None:
        record.result_id = submission.id

    logger.info(
        "Submission created: case=%s submission=%s reviewer=%s unresolved=%d",
        case.id,
        submission.id,
        submission.reviewer_id,
        open_findings,
    )
    return _submission_out(submission)


def _submission_out(submission: Submission) -> SubmissionOut:
    return SubmissionOut(
        submission_id=submission.id,
        case_id=submission.case_id,
        revision=submission.revision,
        analysis_id=submission.analysis_id,
        recipient_id=submission.recipient_id,
        status=submission.state,
        submitted_at=submission.submitted_at,
    )


# --- Reviewer back office ----------------------------------------------------


@router.get(
    "/reviewer/submissions",
    response_model=ListResponse[ReviewerSubmissionSummaryOut],
    summary="List submissions assigned to the signed-in reviewer",
)
def list_reviewer_submissions(
    user: ReviewerDep, db: DbDep
) -> ListResponse[ReviewerSubmissionSummaryOut]:
    """``GET /api/reviewer/submissions`` (spec/backend.md B9, B10).

    Filtered by ``reviewer_id`` in SQL, so another reviewer's inbox can never
    appear. The claimant name comes from the frozen manifest, not from the live
    case.
    """
    submissions = list(
        db.scalars(
            select(Submission)
            .where(Submission.reviewer_id == user.id)
            .order_by(Submission.submitted_at.desc())
        ).all()
    )
    return ListResponse[ReviewerSubmissionSummaryOut](
        items=[
            ReviewerSubmissionSummaryOut(
                submission_id=submission.id,
                case_id=submission.case_id,
                claimant_name=str(
                    submission.manifest.get("claimant_name")
                    or submission.claim_snapshot.get("claimant_name")
                    or "—"
                ),
                revision=submission.revision,
                status=submission.state,
                submitted_at=submission.submitted_at,
            )
            for submission in submissions
        ],
        next_cursor=None,
    )


def _load_assigned_submission(db: DbDep, submission_id: str, user: User) -> Submission:
    """Return the submission if it was assigned to ``user``, else 404 (B10)."""
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id, Submission.reviewer_id == user.id
        )
    )
    if submission is None:
        raise not_found()
    return submission


def _claim_from_snapshot(snapshot: dict[str, object]) -> ClaimOut:
    """Rebuild the frozen claim exactly as it was submitted (spec/backend.md B10)."""
    dates = dict(snapshot.get("dates") or {})  # type: ignore[arg-type]
    return ClaimOut(
        case_type=str(snapshot["case_type"]),  # type: ignore[arg-type]
        claimant_name=str(snapshot["claimant_name"]),
        counterparty_name=str(snapshot["counterparty_name"]),
        claimed_amount=str(snapshot["claimed_amount"]),
        currency=str(snapshot["currency"]),  # type: ignore[arg-type]
        dates=DatesOut(
            contract=dates.get("contract"),  # type: ignore[arg-type]
            delivery=dates.get("delivery"),  # type: ignore[arg-type]
            invoice=dates.get("invoice"),  # type: ignore[arg-type]
            payment_due=dates.get("payment_due"),  # type: ignore[arg-type]
        ),
        requested_outcome=str(snapshot["requested_outcome"]),  # type: ignore[arg-type]
        narrative=str(snapshot["narrative"]),
        follow_up_answers=[
            FollowUpAnswerOut(question_id=str(entry["question_id"]), answer=str(entry["answer"]))
            for entry in (snapshot.get("follow_up_answers") or [])  # type: ignore[union-attr]
        ],
    )


@router.get(
    "/reviewer/submissions/{submission_id}",
    response_model=ReviewerSubmissionDetailOut,
    summary="Open the immutable submitted dossier",
)
def get_reviewer_submission(
    submission_id: str, user: ReviewerDep, db: DbDep
) -> ReviewerSubmissionDetailOut:
    """``GET /api/reviewer/submissions/{id}`` (spec/backend.md B9, B10).

    Serves the **frozen snapshot**, not the current working case: the claim comes
    from ``claim_snapshot``, the documents from the submission manifest, the
    responses from ``response_snapshot``. Later edits by the preparer are invisible
    here, which is the point (BE-14).
    """
    submission = _load_assigned_submission(db, submission_id, user)
    analysis = db.get(Analysis, submission.analysis_id)
    if analysis is None:  # pragma: no cover - FK guarantees it
        raise not_found()

    frozen_documents = submission.manifest.get("documents") or []
    documents: list[DocumentOut] = [
        DocumentOut(
            document_id=str(entry["document_id"]),
            filename=str(entry["filename"]),
            document_type=None,
            pages=entry.get("pages"),  # type: ignore[arg-type]
            uploaded_at=submission.submitted_at,
            state=DocumentState(str(entry.get("state", DocumentState.ready.value))),
            error=None,
            # Frozen at submission time: it was part of the dossier that was sent.
            active=True,
            size_bytes=int(entry.get("size_bytes") or 0),
        )
        for entry in frozen_documents  # type: ignore[union-attr]
    ]

    events = [
        ReviewEventOut(
            event_id=event.id,
            event_type=event.event_type,
            message=event.message,
            created_at=event.created_at,
        )
        for event in db.scalars(
            select(ReviewEvent)
            .where(ReviewEvent.submission_id == submission.id)
            .order_by(ReviewEvent.created_at)
        ).all()
    ]

    responses = []
    for entry in submission.response_snapshot:
        responses.append(
            {
                "finding_id": str(entry["finding_id"]),
                "action": str(entry["action"]),
                "explanation": entry.get("explanation"),
                "document_ids": list(entry.get("document_ids") or []),
                "created_at": str(entry["created_at"]),
            }
        )

    return ReviewerSubmissionDetailOut(
        submission_id=submission.id,
        case_id=submission.case_id,
        revision=submission.revision,
        claim=_claim_from_snapshot(submission.claim_snapshot),
        documents=documents,
        analysis=analysis_out(db, analysis),
        responses=responses,  # type: ignore[arg-type]
        events=events,
    )


@router.post(
    "/reviewer/submissions/{submission_id}/events",
    response_model=ReviewEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a reviewer action on a submission",
)
def create_review_event(
    submission_id: str,
    payload: ReviewEventIn,
    user: ReviewerDep,
    db: DbDep,
    _csrf: CsrfDep,
) -> ReviewEventOut:
    """``POST /api/reviewer/submissions/{id}/events`` (spec/backend.md B9, B10).

    A clarification request is an event, nothing more: the reviewer cannot edit
    evidence or rewrite findings. The preparer revises the working case and submits
    a new version. Received/reviewed states record activity, not legal acceptance.
    """
    submission = _load_assigned_submission(db, submission_id, user)

    event = ReviewEvent(
        id=new_id(EVENT_PREFIX),
        submission_id=submission.id,
        event_type=payload.event_type,
        message=(payload.message or None),
        actor_id=user.id,
    )
    db.add(event)

    if payload.event_type is ReviewEventType.received:
        submission.state = SubmissionState.received
        submission.received_at = utcnow()
    elif payload.event_type is ReviewEventType.clarification_requested:
        submission.state = SubmissionState.clarification_requested
    elif payload.event_type is ReviewEventType.reviewed:
        submission.state = SubmissionState.reviewed
        submission.reviewed_at = utcnow()

    db.flush()
    logger.info(
        "Review event: submission=%s type=%s", submission.id, payload.event_type.value
    )
    return ReviewEventOut(
        event_id=event.id,
        event_type=event.event_type,
        message=event.message,
        created_at=event.created_at,
    )
