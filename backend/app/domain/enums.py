"""Enumerations from the canonical API contract (spec/backend.md B9, B2, B5-B10).

Unknown enum values are rejected at the edge (B9), so every enumerated field in
the contract has exactly one definition here. These are ``str`` enums so they
serialise as the wire value and compare cleanly against stored columns.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Base for wire-facing enums: value is the JSON representation."""

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value


class Role(StrEnum):
    """Server-assigned roles (spec/backend.md B2, B8).

    One preparer role owns cases; one reviewer role receives assigned
    submissions. There is no client-supplied role flag.
    """

    preparer = "preparer"
    reviewer = "reviewer"


class CaseType(StrEnum):
    """Supported case categories (spec/backend.md B2, B3).

    No automatic fallback exists for an unsupported category.
    """

    unpaid_goods_invoice = "unpaid_goods_invoice"


class Currency(StrEnum):
    """Supported currencies (spec/backend.md B2, B7). Never converted."""

    TND = "TND"


class RequestedOutcome(StrEnum):
    """Outcomes a preparer may request (spec/backend.md B2)."""

    payment = "payment"
    payment_plan = "payment_plan"


class IntakeStatus(StrEnum):
    """Cheap-gate result states (spec/backend.md B3, B9)."""

    not_checked = "not_checked"
    ready = "ready"
    needs_information = "needs_information"
    gate_unavailable = "gate_unavailable"


class JobStatus(StrEnum):
    """Durable job states (spec/backend.md B8, B9)."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    superseded = "superseded"


class JobKind(StrEnum):
    """Job families dispatched to the worker (spec/backend.md B8, B9)."""

    analysis = "analysis"
    export = "export"


class JobPhase(StrEnum):
    """Progress phases reported by ``GET /jobs/{id}`` (spec/backend.md B9).

    ``packaging`` belongs to export jobs; the rest belong to analysis jobs.
    """

    reading = "reading"
    extracting = "extracting"
    validating_facts = "validating_facts"
    checking = "checking"
    validating_checks = "validating_checks"
    publishing = "publishing"
    packaging = "packaging"


class DocumentState(StrEnum):
    """Document lifecycle state (spec/backend.md B4)."""

    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    partial = "partial"
    unreadable = "unreadable"
    rejected = "rejected"


class PageMethod(StrEnum):
    """How stored page text was produced (spec/backend.md B4)."""

    embedded_text = "embedded_text"
    ocr = "ocr"


class PageState(StrEnum):
    """Page readability outcome (spec/backend.md B4).

    Stored separately from citation-match status: a quote match proves
    correspondence to stored text, not OCR correctness.
    """

    ready = "ready"
    partial = "partial"
    unreadable = "unreadable"


#: Page quality shares the readability vocabulary (spec/backend.md B4).
PageQuality = PageState


class AnalysisStatus(StrEnum):
    """Published analysis states (spec/backend.md B7, B9).

    Job failure is tracked on the job, not here: invalid output never becomes an
    empty success.
    """

    ready = "ready"
    partial = "partial"
    outdated = "outdated"


class CheckResult(StrEnum):
    """Check outcomes (spec/backend.md B6, B9).

    The model may return only the first three; ``not_applicable`` is owned by
    backend code.
    """

    satisfied = "satisfied"
    contradicted = "contradicted"
    unassessable = "unassessable"
    not_applicable = "not_applicable"


class ReasonCode(StrEnum):
    """Reason codes accompanying a check result (spec/backend.md B6, B9)."""

    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    CONFLICT = "CONFLICT"
    SOURCE_UNREADABLE = "SOURCE_UNREADABLE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    AMBIGUOUS_LINK = "AMBIGUOUS_LINK"
    LEGAL_COVERAGE_UNAVAILABLE = "LEGAL_COVERAGE_UNAVAILABLE"
    INVALID_SOURCE = "INVALID_SOURCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FindingStatus(StrEnum):
    """Finding lifecycle (spec/backend.md B9). Null when no issue ever existed."""

    open = "open"
    resolved = "resolved"


class Delta(StrEnum):
    """Change of a finding between runs (spec/backend.md B7, B9)."""

    new = "new"
    resolved = "resolved"
    still_open = "still_open"
    reopened = "reopened"
    not_applicable = "not_applicable"


class ResponseAction(StrEnum):
    """Preparer responses to a finding (spec/backend.md B9)."""

    add_evidence = "add_evidence"
    correct_claim = "correct_claim"
    explain_unavailable = "explain_unavailable"
    disagree = "disagree"


class LegalCoverage(StrEnum):
    """Whether a reviewed legal pack backs the run (spec/backend.md B5, B9).

    ``unvalidated`` must stay prominently disclosed even for a ready analysis.
    """

    unvalidated = "unvalidated"
    validated = "validated"


class ExecutionMode(StrEnum):
    """Whether a run used fixtures or a live provider (spec/backend.md B9)."""

    fixture = "fixture"
    live = "live"


class SubjectType(StrEnum):
    """Backend-owned stable subject families (spec/backend.md B6, B7).

    The model cannot mint authoritative subjects.
    """

    transaction = "transaction"
    invoice = "invoice"
    payment = "payment"
    credit_note = "credit_note"
    referenced_annex = "referenced_annex"


class FactVerification(StrEnum):
    """Source-match state of a candidate fact (spec/backend.md B7).

    A failed quote match quarantines the fact; dependent judgments cannot be
    published as supported.
    """

    pending = "pending"
    verified = "verified"
    quarantined = "quarantined"


class SubmissionState(StrEnum):
    """Submission lifecycle (spec/backend.md B10).

    Received/reviewed states do not indicate legal acceptance.
    """

    submitted = "submitted"
    received = "received"
    clarification_requested = "clarification_requested"
    reviewed = "reviewed"


class ReviewEventType(StrEnum):
    """Reviewer event types (spec/backend.md B9, B10)."""

    received = "received"
    clarification_requested = "clarification_requested"
    reviewed = "reviewed"


class ExportState(StrEnum):
    """Export package lifecycle (spec/backend.md B10)."""

    generating = "generating"
    ready = "ready"
    failed = "failed"


class ClaimOrigin(StrEnum):
    """Provenance of typed claim data (spec/backend.md B3).

    Typed claim data is ``user_claim`` and must never receive fabricated
    document/page provenance.
    """

    user_claim = "user_claim"


__all__ = [
    "AnalysisStatus",
    "CaseType",
    "CheckResult",
    "ClaimOrigin",
    "Currency",
    "Delta",
    "DocumentState",
    "ExecutionMode",
    "ExportState",
    "FactVerification",
    "FindingStatus",
    "IntakeStatus",
    "JobKind",
    "JobPhase",
    "JobStatus",
    "LegalCoverage",
    "PageMethod",
    "PageQuality",
    "PageState",
    "ReasonCode",
    "RequestedOutcome",
    "ResponseAction",
    "ReviewEventType",
    "Role",
    "StrEnum",
    "SubjectType",
    "SubmissionState",
]
