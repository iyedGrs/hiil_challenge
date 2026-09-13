"""Row-to-contract projections shared by the routers (spec/backend.md B9).

Every response body in the contract is built here so two routes can never
disagree about a field name, and so the mapping between storage vocabulary
(``display_name``, ``is_active``, ``page_count``) and wire vocabulary
(``filename``, ``active``, ``pages``) lives in exactly one place.

Nothing in this module reads model output, provider payloads or unvalidated
facts: it projects already-persisted, already-validated rows (B7).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain.enums import PageState, ResponseAction
from app.models.analysis import Analysis, CheckResultRow
from app.models.case import ClaimRevision
from app.models.document import Document, Page
from app.models.fact import Extraction
from app.models.finding import FindingResponse
from app.models.job import Job
from app.models.legal import Check
from app.models.subject import Subject
from app.pipeline.readiness import Readiness, case_readiness
from app.schemas.analyses import AnalysisOut, CheckOut, CoverageOut, EvidenceRefOut, ReconciliationOut
from app.schemas.cases import ClaimOut, DatesOut, FollowUpAnswerOut, IntakeOut, IntakeQuestionOut
from app.schemas.common import decimal_to_string
from app.schemas.documents import DocumentOut, PageOut
from app.schemas.findings import FindingResponseOut
from app.schemas.jobs import JobOut
from app.schemas.readiness import ReadinessOut


def document_types(db: DbSession, document_ids: list[str]) -> dict[str, str | None]:
    """Return the server-classified document type for each of ``document_ids``.

    The classification lives on the cached :class:`Extraction` row rather than on
    the document, because it is produced by the analysis pipeline and may be
    recomputed under a new extraction/schema version. Documents that have not
    been through extraction yet simply have no type.
    """
    if not document_ids:
        return {}
    rows = db.execute(
        select(Extraction.document_id, Extraction.document_type, Extraction.created_at)
        .where(Extraction.document_id.in_(document_ids))
        .order_by(Extraction.document_id, Extraction.created_at)
    ).all()
    # Later rows for the same document win, so the newest extraction's
    # classification is the one reported.
    return {row[0]: row[1] for row in rows}


def document_out(document: Document, document_type: str | None = None) -> DocumentOut:
    """Project one document row onto the contract shape (B4, B9)."""
    return DocumentOut(
        document_id=document.id,
        filename=document.display_name,
        document_type=document_type,
        pages=document.page_count,
        uploaded_at=document.created_at,
        state=document.state,
        error=document.rejection_message,
        active=document.is_active,
        size_bytes=document.byte_size,
    )


def documents_out(db: DbSession, documents: list[Document]) -> list[DocumentOut]:
    """Project many documents, resolving their types in one query."""
    types = document_types(db, [document.id for document in documents])
    return [document_out(document, types.get(document.id)) for document in documents]


def page_image_url(page: Page) -> str | None:
    """Authorized rendered-page URL, or ``None`` when no image was rendered."""
    if page.image_key is None:
        return None
    return f"/api/documents/{page.document_id}/pages/{page.page_number}/image"


def page_out(page: Page) -> PageOut:
    """Project one page row onto the contract shape (B4, B9).

    ``source_text`` is ``None`` rather than an empty string for an unreadable
    page, so the UI shows "no source text" instead of an empty quote box.
    """
    text = page.text.strip()
    return PageOut(
        document_id=page.document_id,
        page=page.page_number,
        image_url=page_image_url(page),
        source_text=page.text if text else None,
        method=page.method,
        quality=page.state.value if isinstance(page.state, PageState) else str(page.state),
    )


def job_out(job: Job) -> JobOut:
    """Project one job row onto ``GET /api/jobs/{id}`` (B9).

    ``error`` carries the sanitized stored message only; ``phase`` and both
    result IDs are nullable by contract.
    """
    return JobOut(
        id=job.id,
        status=job.status,
        phase=job.phase,
        error=job.error_message,
        result_analysis_id=job.result_analysis_id,
        result_export_id=job.result_export_id,
    )


def claim_out(revision: ClaimRevision) -> ClaimOut:
    """Project a stored claim revision onto the canonical claim shape (B9).

    Amounts are rendered from the numeric column as canonical decimal strings;
    they are never emitted as JSON floats (B3, B7). All four date keys are
    always present and ``null`` means "not known" (B3).
    """
    amount: Decimal = revision.claimed_amount
    return ClaimOut(
        case_type=revision.case_type,
        claimant_name=revision.claimant_name,
        counterparty_name=revision.counterparty_name,
        claimed_amount=decimal_to_string(amount),
        currency=revision.currency,
        dates=DatesOut(
            contract=revision.date_contract,
            delivery=revision.date_delivery,
            invoice=revision.date_invoice,
            payment_due=revision.date_payment_due,
        ),
        requested_outcome=revision.requested_outcome,
        narrative=revision.narrative,
        follow_up_answers=[
            FollowUpAnswerOut(question_id=entry["question_id"], answer=entry["answer"])
            for entry in revision.follow_up_answers
        ],
    )


def intake_out(revision: ClaimRevision) -> IntakeOut:
    """Project the cached cheap-gate result for one claim revision (B3, B9)."""
    return IntakeOut(
        status=revision.intake_status,
        questions=[
            IntakeQuestionOut(
                id=question["id"], field=question["field"], message=question["message"]
            )
            for question in revision.intake_questions
        ],
    )


def _subject_labels(db: DbSession, case_id: str) -> dict[str, str]:
    """Return the plain-language label for every subject in ``case_id``.

    Findings must show a readable subject next to the opaque ``subject_id``
    (frontend.md F4). A subject with no stored label falls back to its own ID,
    which is already human-readable by construction (``invoice_0001``).
    """
    rows = db.execute(
        select(Subject.subject_id, Subject.label).where(Subject.case_id == case_id)
    ).all()
    return {row[0]: (row[1] or row[0]) for row in rows}


def _check_sort_orders(db: DbSession, pack_version: str) -> dict[str, int]:
    """Return the checklist's own display order for one pack version (B5)."""
    rows = db.execute(
        select(Check.check_id, Check.sort_order).where(Check.pack_version == pack_version)
    ).all()
    return {row[0]: row[1] for row in rows}


def analysis_out(db: DbSession, analysis: Analysis) -> AnalysisOut:
    """Project one published analysis onto ``GET /api/analyses/{id}`` (B9).

    Checks are ordered by the reviewed checklist's own ``sort_order`` and then by
    subject ID, so the same run always renders in the same order and the order
    carries the checklist author's intent rather than insertion timing.

    ``legal_coverage`` is copied from the run: a stored ``unvalidated`` value
    stays visible even when the run is otherwise ready (B5, B10).
    """
    labels = _subject_labels(db, analysis.case_id)
    sort_orders = _check_sort_orders(db, analysis.checklist_version)

    rows = list(
        db.scalars(
            select(CheckResultRow).where(CheckResultRow.analysis_id == analysis.id)
        ).all()
    )
    rows.sort(key=lambda row: (sort_orders.get(row.check_id, 10_000), row.check_id, row.subject_id))

    checks = [
        CheckOut(
            check_id=row.check_id,
            subject_id=row.subject_id,
            subject_label=labels.get(row.subject_id, row.subject_id),
            finding_id=row.finding_id or "",
            result=row.result,
            reason_code=row.reason_code,
            finding_status=row.finding_status,
            delta=row.delta,
            basis=row.basis,
            message=row.message,
            evidence_refs=[
                EvidenceRefOut(
                    fact_id=str(ref["fact_id"]),
                    document_id=str(ref["document_id"]),
                    page=int(ref["page"]),
                    source_text=str(ref["source_text"]),
                )
                for ref in row.evidence_refs
            ],
            reviewed_document_ids=list(row.reviewed_document_ids),
            legal_reference_ids=list(row.legal_reference_ids),
            actions=[ResponseAction(action) for action in row.actions],
        )
        for row in rows
    ]

    coverage = analysis.coverage or {}
    reconciliation: ReconciliationOut | None = None
    if analysis.reconciliation:
        payload = analysis.reconciliation
        reconciliation = ReconciliationOut(
            documented_balance=str(payload["documented_balance"]),
            currency=str(payload["currency"]),
            source_fact_ids=list(payload.get("source_fact_ids", [])),
            coverage_note=str(payload.get("coverage_note", "")),
        )

    return AnalysisOut(
        analysis_id=analysis.id,
        case_id=analysis.case_id,
        revision=analysis.revision,
        status=analysis.status,
        execution_mode=analysis.execution_mode,
        checklist_version=analysis.checklist_version,
        legal_coverage=analysis.legal_coverage,
        coverage=CoverageOut(
            reviewed_pages=int(coverage.get("reviewed_pages", 0)),
            unreadable_pages=int(coverage.get("unreadable_pages", 0)),
            rejected_facts=int(coverage.get("rejected_facts", 0)),
        ),
        checks=checks,
        reconciliation=reconciliation,
    )


def readiness_out(readiness: Readiness) -> ReadinessOut:
    """Project a computed :class:`Readiness` onto the wire shape."""
    return ReadinessOut(status=readiness.status, reasons=readiness.reasons)


def case_readiness_out(db: DbSession, *, case_revision: int, analysis: Analysis | None) -> ReadinessOut:
    """Compute and project the case's automatic readiness verdict."""
    return readiness_out(case_readiness(db, case_revision=case_revision, analysis=analysis))


def finding_response_out(response: FindingResponse) -> FindingResponseOut:
    """Project one saved preparer response (spec/backend.md B9)."""
    return FindingResponseOut(
        finding_id=response.finding_id,
        action=response.action,
        explanation=response.explanation,
        document_ids=list(response.document_ids),
        created_at=response.created_at,
    )
