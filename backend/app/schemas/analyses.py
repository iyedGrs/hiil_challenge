"""Published analysis schemas (spec/backend.md B6, B7, B9).

Only validated, publishable data appears here: no raw candidate facts, no model
explanations presented as findings and no model-supplied legal IDs (B9).
``legal_reference_ids`` always originates in the reviewed checklist (B5).

Every monetary value is a decimal string produced by ``Decimal`` code; the model
never emits a balance (B7).
"""

from __future__ import annotations

from app.domain.enums import (
    AnalysisStatus,
    CheckResult,
    Delta,
    ExecutionMode,
    FindingStatus,
    LegalCoverage,
    ReasonCode,
    ResponseAction,
)
from app.schemas.common import ResponseModel


class EvidenceRefOut(ResponseModel):
    """A validated citation: ``{fact_id, document_id, page, source_text}`` (B9).

    ``source_text`` was located in the stored page text of ``document_id`` page
    ``page`` before this run was published (B7). A match proves correspondence to
    stored text, not that the interpretation is correct.
    """

    fact_id: str
    document_id: str
    page: int
    source_text: str


class CheckOut(ResponseModel):
    """One published check/subject judgment (spec/backend.md B9).

    ``result`` is one of the model's three outcomes plus code-owned
    ``not_applicable``. ``reason_code`` qualifies it: ``EVIDENCE_NOT_FOUND``
    means "not found in the assessed material", and where an unreadable page or
    a quarantined extraction could contain the item the run publishes
    ``PARTIAL_COVERAGE``/``SOURCE_UNREADABLE`` instead of an unqualified absence
    claim (B6).

    ``message`` is backend-rendered copy; the model's own wording is never
    published as the finding text.
    """

    check_id: str
    subject_id: str
    #: Plain-language subject label the preparer reads (frontend.md F4).
    subject_label: str
    finding_id: str
    result: CheckResult
    reason_code: ReasonCode
    finding_status: FindingStatus | None
    delta: Delta | None
    basis: str
    message: str
    evidence_refs: list[EvidenceRefOut]
    reviewed_document_ids: list[str]
    legal_reference_ids: list[str]
    actions: list[ResponseAction]


class ReconciliationOut(ResponseModel):
    """Backend-generated deterministic reconciliation (spec/backend.md B7).

    Present only when every input and link is unambiguous. The balance is
    computed by ``Decimal`` code from validated source facts and is always
    labelled as based on the uploaded records -- an absent receipt is not proof
    that nothing was paid.
    """

    documented_balance: str
    currency: str
    source_fact_ids: list[str]
    coverage_note: str


class CoverageOut(ResponseModel):
    """Processing manifest computed from actual work done (spec/backend.md B6)."""

    reviewed_pages: int
    unreadable_pages: int
    rejected_facts: int


class AnalysisOut(ResponseModel):
    """``GET /api/analyses/{id}`` (spec/backend.md B9).

    ``legal_coverage=unvalidated`` stays present even on an otherwise ready
    analysis, so the disclosure cannot be dropped downstream (B5, B10).
    """

    analysis_id: str
    case_id: str
    revision: int
    status: AnalysisStatus
    execution_mode: ExecutionMode
    checklist_version: str
    legal_coverage: LegalCoverage
    coverage: CoverageOut
    checks: list[CheckOut]
    reconciliation: ReconciliationOut | None
