"""Analysis job handler (spec/backend.md B6, B7, B8).

Orchestrates one assessment run for one case revision:

``reading`` -> ``extracting`` -> ``validating_facts`` -> ``checking``
-> ``validating_checks`` -> ``publishing``

Design points worth knowing before changing this file:

* **The run is pinned to a revision.** ``job.input_revision`` is the snapshot. If
  the working case moved on while the job was in flight, the job ends
  ``superseded`` and nothing is published; a run can never finalize a newer
  revision (B7, BE-11).
* **Phase updates are committed as they happen.** That is a deliberate exception
  to "the handler owns no transaction boundary": progress has to be visible to
  ``GET /jobs/{id}`` while the job runs. It also makes extraction results durable
  before publication, which is exactly what B8 wants -- a retry reuses completed
  extraction instead of paying for it twice.
* **Publication is still atomic.** Everything in the publishing phase is one flush
  committed by the worker loop, so a failure leaves no half-published run (B7).
* **A provider failure is a failure.** It is recorded and surfaced; it never
  degrades into fixture output or an empty success (L3, BE-13).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ai import get_adapter
from app.ai.base import (
    AiResponseInvalidError,
    AiUnavailableError,
    CheckRequest,
    ClaimInput,
    ValidatedFactInput,
)
from app.ai.contracts import PROMPT_VERSION
from app.config import get_settings
from app.domain.enums import (
    ExecutionMode,
    JobPhase,
    JobStatus,
    LegalCoverage,
    PageState,
)
from app.errors import PROVIDER_UNAVAILABLE, ApiError
from app.models.base import utcnow
from app.models.case import Case, ClaimRevision
from app.models.document import Document, Page
from app.models.fact import Fact
from app.models.job import Job
from app.models.legal import LegalPack
from app.models.subject import Subject
from app.money import parse_claim_amount
from app.normalization import NORMALIZATION_VERSION
from app.pipeline import facts as facts_module
from app.pipeline import subjects as subjects_module
from app.pipeline.publish import Coverage, instantiate_checks, publish_run, validate_judgments
from app.pipeline.reconcile import reconcile

logger = logging.getLogger("app.pipeline.analysis")

#: Disclosure flags attached to a published run (spec/backend.md B7, B10).
DISCLOSURE_UNVALIDATED_LEGAL = "legal_coverage_unvalidated"
DISCLOSURE_PARTIAL_COVERAGE = "partial_coverage"
DISCLOSURE_FIXTURE_MODE = "fixture_execution_mode"


def _set_phase(db: DbSession, job: Job, phase: JobPhase) -> None:
    """Record the current phase and commit so polling can observe it (B9)."""
    job.phase = phase
    db.commit()


def _mark_superseded(db: DbSession, job: Job) -> None:
    """End the job as ``superseded`` because the case moved on (B7).

    The lease is released here so the worker's success path does not overwrite the
    status: ``_release_success`` only promotes a job that is still ``running``.
    """
    job.status = JobStatus.superseded
    job.phase = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.finished_at = utcnow()
    db.commit()
    logger.info("Job %s superseded: case revision moved past %d", job.id, job.input_revision)


def handle_analysis_job(db: DbSession, job: Job) -> None:
    """Run one analysis job to publication (spec/backend.md B6, B7, B8)."""
    settings = get_settings()
    adapter = get_adapter(settings)

    case = db.get(Case, job.case_id)
    if case is None:  # pragma: no cover - FK guarantees the case exists
        raise ApiError("INTERNAL_ERROR", "The case for this job no longer exists.")

    if case.revision != job.input_revision:
        _mark_superseded(db, job)
        return

    claim = db.get(ClaimRevision, (case.id, job.input_revision))
    if claim is None:
        claim = db.scalar(
            select(ClaimRevision)
            .where(ClaimRevision.case_id == case.id)
            .order_by(ClaimRevision.revision.desc())
            .limit(1)
        )
    if claim is None:  # pragma: no cover - a case always has revision 1
        raise ApiError("INTERNAL_ERROR", "The claim revision for this job is missing.")

    # --- reading ------------------------------------------------------------
    _set_phase(db, job, JobPhase.reading)
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case.id, Document.is_active.is_(True))
            .order_by(Document.created_at)
        ).all()
    )
    pages_by_document: dict[str, list[Page]] = {}
    for document in documents:
        pages_by_document[document.id] = list(
            db.scalars(
                select(Page)
                .where(Page.document_id == document.id)
                .order_by(Page.page_number)
            ).all()
        )

    all_pages = [page for pages in pages_by_document.values() for page in pages]
    reviewed_pages = sum(1 for page in all_pages if page.state is not PageState.unreadable)
    unreadable_pages = sum(1 for page in all_pages if page.state is PageState.unreadable)
    reviewed_document_ids = [
        document.id
        for document in documents
        if any(
            page.state is not PageState.unreadable for page in pages_by_document[document.id]
        )
    ]

    # --- extracting + validating_facts -------------------------------------
    _set_phase(db, job, JobPhase.extracting)
    verified: list[Fact] = []
    rejected_facts = 0
    last_extraction = None
    try:
        for document in documents:
            outcome = facts_module.extract_document(
                db,
                case_id=case.id,
                document=document,
                pages=pages_by_document[document.id],
                adapter=adapter,
            )
            verified.extend(outcome.verified)
            rejected_facts += outcome.rejected_count
            last_extraction = outcome.extraction
    except AiUnavailableError as exc:
        raise ApiError(PROVIDER_UNAVAILABLE, str(exc), retryable=True) from exc
    except AiResponseInvalidError as exc:
        raise ApiError("PROVIDER_SCHEMA_INVALID", str(exc), status=502, retryable=False) from exc

    _set_phase(db, job, JobPhase.validating_facts)
    if case.revision != job.input_revision:
        _mark_superseded(db, job)
        return

    subject_set = subjects_module.build_subjects(
        db,
        case_id=case.id,
        claim=claim,
        revision=job.input_revision,
        verified_facts=verified,
    )
    subjects_module.deactivate_missing_subjects(
        db,
        case_id=case.id,
        active_subject_ids={subject.subject_id for subject in subject_set.all_active},
    )
    all_subjects = list(
        db.scalars(select(Subject).where(Subject.case_id == case.id)).all()
    )
    subjects_by_id = {subject.subject_id: subject for subject in all_subjects}

    coverage = Coverage(
        reviewed_pages=reviewed_pages,
        unreadable_pages=unreadable_pages,
        rejected_facts=rejected_facts,
    )

    instantiation = instantiate_checks(
        db,
        case_id=case.id,
        case_type=case.case_type.value,
        pack_version=job.payload.get("checklist_version") or settings.legal_pack_version,
        subjects=all_subjects,
    )

    # --- checking -----------------------------------------------------------
    _set_phase(db, job, JobPhase.checking)
    document_inputs = tuple(
        facts_module.document_input(document, pages_by_document[document.id])
        for document in documents
    )
    fact_inputs = tuple(
        ValidatedFactInput(
            fact_id=fact.id,
            kind=fact.kind,
            value_text=fact.value_text,
            currency_text=fact.currency_text,
            document_id=fact.document_id,
            page=fact.page,
            source_text=fact.source_text,
            subject_id=fact.subject_id,
        )
        for fact in verified
    )
    request = CheckRequest(
        claim=ClaimInput(
            case_type=claim.case_type.value,
            claimant_name=claim.claimant_name,
            counterparty_name=claim.counterparty_name,
            claimed_amount=str(claim.claimed_amount),
            currency=claim.currency.value,
            requested_outcome=claim.requested_outcome.value,
            narrative=claim.narrative,
            dates={
                "contract": claim.date_contract.isoformat() if claim.date_contract else None,
                "delivery": claim.date_delivery.isoformat() if claim.date_delivery else None,
                "invoice": claim.date_invoice.isoformat() if claim.date_invoice else None,
                "payment_due": (
                    claim.date_payment_due.isoformat() if claim.date_payment_due else None
                ),
            },
        ),
        documents=document_inputs,
        facts=fact_inputs,
        checks=tuple(instantiation.model_checks),
    )

    try:
        response = adapter.judge_checks(request)
    except AiUnavailableError as exc:
        raise ApiError(PROVIDER_UNAVAILABLE, str(exc), retryable=True) from exc
    except AiResponseInvalidError as exc:
        raise ApiError("PROVIDER_SCHEMA_INVALID", str(exc), status=502, retryable=False) from exc

    # --- validating_checks --------------------------------------------------
    _set_phase(db, job, JobPhase.validating_checks)

    if response.monetary_facts and last_extraction is not None:
        # Stage 2 may only repeat or newly extract *source* amounts, and they face
        # exactly the same provenance gate as Stage 1 (B6).
        new_verified, new_quarantined = facts_module.validate_stage2_facts(
            db,
            case_id=case.id,
            extraction=last_extraction,
            candidates=list(response.monetary_facts),
            documents_by_id={document.id: document for document in documents},
            pages_by_document={
                document_id: {page.page_number: page for page in pages}
                for document_id, pages in pages_by_document.items()
            },
            existing=verified,
            adapter=adapter,
        )
        if new_verified:
            subjects_module.build_subjects(
                db,
                case_id=case.id,
                claim=claim,
                revision=job.input_revision,
                verified_facts=new_verified,
            )
        verified.extend(new_verified)
        rejected_facts += len(new_quarantined)
        coverage = Coverage(
            reviewed_pages=reviewed_pages,
            unreadable_pages=unreadable_pages,
            rejected_facts=rejected_facts,
        )

    verified_fact_ids = {fact.id for fact in verified}
    judgments, problems = validate_judgments(
        instantiation=instantiation,
        response=response,
        verified_fact_ids=verified_fact_ids,
        coverage=coverage,
    )
    for problem in problems:
        # Sanitized: the reason only, never the rejected payload (B9, L6).
        logger.warning("Stage 2 validation: %s", problem)

    reconciliation = reconcile(
        claimed_amount=parse_claim_amount(str(claim.claimed_amount)),
        currency=claim.currency.value,
        verified_facts=verified,
        subjects_by_id=subjects_by_id,
    )

    # --- publishing ---------------------------------------------------------
    _set_phase(db, job, JobPhase.publishing)
    if case.revision != job.input_revision:
        _mark_superseded(db, job)
        return

    pack = db.get(LegalPack, settings.legal_pack_version)
    # No loaded pack means no validated legal coverage; B5 requires disabling the
    # claim rather than assuming it.
    legal_coverage = pack.coverage if pack is not None else LegalCoverage.unvalidated
    execution_mode = ExecutionMode(adapter.execution_mode)

    disclosures: list[str] = []
    if legal_coverage is LegalCoverage.unvalidated:
        disclosures.append(DISCLOSURE_UNVALIDATED_LEGAL)
    if coverage.is_partial:
        disclosures.append(DISCLOSURE_PARTIAL_COVERAGE)
    if execution_mode is ExecutionMode.fixture:
        disclosures.append(DISCLOSURE_FIXTURE_MODE)

    input_snapshot: dict[str, object] = {
        "claim_revision": job.input_revision,
        "documents": [
            {"document_id": document.id, "sha256": document.sha256, "pages": document.page_count}
            for document in documents
        ],
        "page_ids": [page.id for page in all_pages],
        "extraction_version": facts_module.EXTRACTION_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_version": adapter.model_version,
    }

    analysis = publish_run(
        db,
        case_id=case.id,
        revision=job.input_revision,
        execution_mode=execution_mode,
        checklist_version=settings.legal_pack_version,
        legal_coverage=legal_coverage,
        model_version=adapter.model_version,
        prompt_version=PROMPT_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        input_snapshot=input_snapshot,
        coverage=coverage,
        instantiation=instantiation,
        judgments=judgments,
        reconciliation=reconciliation,
        facts_by_id={fact.id: fact for fact in verified},
        reviewed_document_ids=reviewed_document_ids,
        job_id=job.id,
        disclosures=disclosures,
    )

    job.result_analysis_id = analysis.id
    db.flush()
