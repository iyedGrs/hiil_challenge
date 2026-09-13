"""Analysis, job and findings-response routes (spec/backend.md B7, B8, B9).

``POST /api/cases/{id}/analyses`` only *enqueues* work. Everything expensive
happens in the worker, so the request returns 202 immediately and the client polls
``GET /api/jobs/{id}``. Guards applied before a job is created, in order:

1. ownership + row lock, then ``expected_revision`` (409 ``REVISION_CONFLICT``);
2. idempotency replay (returns the original job rather than a second run);
3. the cheap gate must be ``ready`` (409 ``INTAKE_NOT_READY``, with the saved
   questions in ``field_errors`` so the UI renders targeted follow-up instead of a
   pipeline failure);
4. one active assessment per case (409 ``ANALYSIS_ALREADY_RUNNING``).

``GET /api/analyses/{id}`` serves only published runs; a pending one answers 409
``ANALYSIS_NOT_PUBLISHED`` rather than an empty success (B7).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from app.api.access import current_claim_revision, load_owned_case, require_matching_revision
from app.api.deps import CsrfDep, DbDep, PreparerDep
from app.api.idempotency import (
    SCOPE_ANALYSIS,
    fingerprint,
    idempotency_key_header,
    reuse_or_claim,
)
from app.api.views import analysis_out, finding_response_out, job_out
from app.config import get_settings
from app.domain.enums import IntakeStatus, JobKind, JobStatus
from app.errors import (
    ANALYSIS_ALREADY_RUNNING,
    ANALYSIS_NOT_PUBLISHED,
    INTAKE_NOT_READY,
    ApiError,
    FieldError,
    not_found,
)
from app.ids import JOB_PREFIX, RESPONSE_PREFIX, new_id
from app.models.analysis import Analysis
from app.models.case import Case
from app.models.document import Document
from app.models.finding import Finding, FindingResponse
from app.models.job import Job
from app.schemas.analyses import AnalysisOut
from app.schemas.cases import RevisionIn
from app.schemas.findings import FindingResponseIn, FindingResponseResult
from app.schemas.jobs import JobOut, StartAnalysisOut

logger = logging.getLogger("app.api.analyses")

router = APIRouter(tags=["analyses"])

#: Job states that still occupy the case's single assessment slot (B8).
ACTIVE_JOB_STATES = (JobStatus.queued, JobStatus.running)


@router.post(
    "/cases/{case_id}/analyses",
    response_model=StartAnalysisOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an assessment of the current case revision",
)
def start_analysis(
    case_id: str,
    payload: RevisionIn,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
    response: Response,
    idempotency_key: str | None = Depends(idempotency_key_header),
) -> StartAnalysisOut:
    """``POST /api/cases/{id}/analyses`` -> 202 ``{job_id, case_id, revision}`` (B9)."""
    settings = get_settings()
    case = load_owned_case(db, case_id, user, lock=True)
    require_matching_revision(case, payload.expected_revision)

    request_fingerprint = fingerprint(
        {"case_id": case.id, "revision": payload.expected_revision, "scope": SCOPE_ANALYSIS}
    )
    record, is_replay = reuse_or_claim(
        db,
        case_id=case.id,
        scope=SCOPE_ANALYSIS,
        key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if is_replay and record is not None and record.job_id is not None:
        response.status_code = status.HTTP_200_OK
        return StartAnalysisOut(
            job_id=record.job_id, case_id=case.id, revision=payload.expected_revision
        )

    claim = current_claim_revision(db, case)
    if claim.intake_status is not IntakeStatus.ready:
        # The saved questions travel in field_errors so the UI can render targeted
        # follow-up rather than reporting a failed pipeline (B9, FE-02).
        raise ApiError(
            INTAKE_NOT_READY,
            "More information is needed before the documents can be assessed.",
            field_errors=[
                FieldError(question["field"], question["message"])
                for question in claim.intake_questions
            ],
        )

    running = db.scalar(
        select(Job).where(
            Job.case_id == case.id,
            Job.kind == JobKind.analysis,
            Job.status.in_(ACTIVE_JOB_STATES),
        )
    )
    if running is not None:
        raise ApiError(
            ANALYSIS_ALREADY_RUNNING,
            "An assessment is already running for this case.",
        )

    job = Job(
        id=new_id(JOB_PREFIX),
        case_id=case.id,
        kind=JobKind.analysis,
        status=JobStatus.queued,
        idempotency_key=idempotency_key or f"auto-{new_id(JOB_PREFIX)}",
        input_revision=case.revision,
        execution_mode=settings.ai_mode.value,
        payload={"checklist_version": settings.legal_pack_version},
        requested_by=user.id,
    )
    db.add(job)
    db.flush()
    if record is not None:
        record.job_id = job.id

    logger.info("Analysis queued: case=%s job=%s revision=%d", case.id, job.id, case.revision)
    return StartAnalysisOut(job_id=job.id, case_id=case.id, revision=case.revision)


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Poll one job's progress")
def get_job(job_id: str, user: PreparerDep, db: DbDep) -> JobOut:
    """``GET /api/jobs/{id}`` (spec/backend.md B9).

    Owner-scoped through the job's case. A transport error on the client stops
    neither the job nor its stored progress, which is why this route is a plain
    read of durable state (frontend.md F4).
    """
    job = db.scalar(
        select(Job)
        .join(Case, Case.id == Job.case_id)
        .where(Job.id == job_id, Case.owner_id == user.id)
    )
    if job is None:
        raise not_found()
    return job_out(job)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    summary="Read one published analysis",
)
def get_analysis(analysis_id: str, user: PreparerDep, db: DbDep) -> AnalysisOut:
    """``GET /api/analyses/{id}`` (spec/backend.md B9).

    A run that exists but was never published answers 409
    ``ANALYSIS_NOT_PUBLISHED``: an unpublished run is not an empty result (B7).
    """
    analysis = db.scalar(
        select(Analysis)
        .join(Case, Case.id == Analysis.case_id)
        .where(Analysis.id == analysis_id, Case.owner_id == user.id)
    )
    if analysis is None:
        raise not_found()
    if analysis.published_at is None:
        raise ApiError(
            ANALYSIS_NOT_PUBLISHED,
            "This assessment has not finished publishing yet.",
        )
    return analysis_out(db, analysis)


@router.post(
    "/findings/{finding_id}/responses",
    response_model=FindingResponseResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record a preparer response to a finding",
)
def create_finding_response(
    finding_id: str,
    payload: FindingResponseIn,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
) -> FindingResponseResult:
    """``POST /api/findings/{id}/responses`` (spec/backend.md B7, B9).

    Saving a response bumps the case revision, because the evidence set or the
    preparer's position changed and any existing analysis is now stale.

    A response never resolves the finding. Only the next validated assessment
    decides its state, and a disagreement stays visible in history and in the
    submitted snapshot (B7, FE-06).
    """
    finding = db.scalar(
        select(Finding)
        .join(Case, Case.id == Finding.case_id)
        .where(Finding.id == finding_id, Case.owner_id == user.id)
    )
    if finding is None:
        raise not_found()

    case = load_owned_case(db, finding.case_id, user, lock=True)
    require_matching_revision(case, payload.expected_revision)

    # Attached evidence must already belong to this case; a response never
    # introduces a document from anywhere else (frontend.md F4).
    document_ids = list(dict.fromkeys(payload.document_ids))
    if document_ids:
        owned = set(
            db.scalars(
                select(Document.id).where(
                    Document.id.in_(document_ids),
                    Document.case_id == case.id,
                    Document.is_active.is_(True),
                )
            ).all()
        )
        missing = [document_id for document_id in document_ids if document_id not in owned]
        if missing:
            raise ApiError(
                "INVALID_INPUT",
                "One or more attached documents do not belong to this case.",
                field_errors=[
                    FieldError("document_ids", "This document is not an active file of the case.")
                ],
            )

    new_revision = case.revision + 1
    case.revision = new_revision

    latest_analysis_id = db.scalar(
        select(Analysis.id)
        .where(Analysis.case_id == case.id)
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )

    row = FindingResponse(
        id=new_id(RESPONSE_PREFIX),
        finding_id=finding.id,
        case_id=case.id,
        revision=new_revision,
        analysis_id=latest_analysis_id,
        action=payload.action,
        explanation=(payload.explanation or None),
        document_ids=document_ids,
        created_by=user.id,
    )
    db.add(row)
    db.flush()

    logger.info(
        "Finding response saved: finding=%s action=%s revision=%d",
        finding.id,
        payload.action.value,
        new_revision,
    )
    return FindingResponseResult(revision=new_revision, response=finding_response_out(row))
