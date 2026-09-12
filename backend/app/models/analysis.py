"""Published analyses and validated check results (spec/backend.md B6, B7, B9).

A run uses an immutable ``input_snapshot``. If the working case changes during
processing the historical run is retained, its job becomes ``superseded`` and the
analysis becomes ``outdated``; it can never finalize a newer revision (B7).

Publication is atomic and happens only after validation, so invalid model output
never becomes an empty success (B7). Rows here hold validated, publishable data:
no raw candidate facts and no model-supplied legal IDs (B9).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AnalysisStatus,
    CheckResult,
    Delta,
    ExecutionMode,
    FindingStatus,
    LegalCoverage,
    ReasonCode,
)
from app.models.base import (
    Base,
    JsonType,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Analysis(Base, TimestampMixin):
    """One published assessment run (spec/backend.md B7, B9).

    ``coverage`` carries the computed manifest (reviewed/unreadable pages,
    rejected facts) derived from actual processing, not from a model claim to
    have reviewed all files (B6).
    """

    __tablename__ = "analyses"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    #: Case revision this run assessed; publication cannot move it forward (B7).
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(enum_type(AnalysisStatus), nullable=False)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode), nullable=False
    )
    checklist_version: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_coverage: Mapped[LegalCoverage] = mapped_column(
        enum_type(LegalCoverage), nullable=False, default=LegalCoverage.unvalidated
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Frozen inputs: claim revision, document IDs/hashes, page IDs, versions.
    input_snapshot: Mapped[dict[str, object]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    coverage: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    #: Backend-generated deterministic reconciliation, or null when not resolved.
    reconciliation: Mapped[dict[str, object] | None] = mapped_column(JsonType, nullable=True)
    #: Disclosure flags, e.g. unvalidated legal coverage or partial coverage.
    disclosures: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    reviewed_document_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    check_results: Mapped[list["CheckResultRow"]] = relationship(back_populates="analysis")

    __table_args__ = (
        Index("ix_analyses_case_id_created_at", "case_id", "created_at"),
        Index("ix_analyses_case_id_revision", "case_id", "revision"),
    )


class CheckResultRow(Base):
    """A validated check/subject judgment inside one run (spec/backend.md B6, B9).

    The primary key ``(analysis_id, check_id, subject_id)`` mirrors the contract:
    only supplied check/subject pairs may appear, and unknown or duplicate pairs
    are rejected before persistence. ``legal_reference_ids`` is copied from the
    reviewed checklist, never from model output (B5).
    """

    __tablename__ = "check_results"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    result: Mapped[CheckResult] = mapped_column(enum_type(CheckResult), nullable=False)
    reason_code: Mapped[ReasonCode] = mapped_column(enum_type(ReasonCode), nullable=False)
    #: Null when no issue ever existed for this pair (spec/backend.md B9).
    finding_status: Mapped[FindingStatus | None] = mapped_column(
        enum_type(FindingStatus), nullable=True
    )
    delta: Mapped[Delta | None] = mapped_column(enum_type(Delta), nullable=True)
    basis: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Backend-rendered message; model explanations stay in ``explanation``.
    message: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``{fact_id, document_id, page, source_text}`` entries (B9).
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    fact_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    reviewed_document_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    legal_reference_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    actions: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    created_at: Mapped[datetime] = created_at_column()

    analysis: Mapped[Analysis] = relationship(back_populates="check_results")

    __table_args__ = (
        PrimaryKeyConstraint("analysis_id", "check_id", "subject_id", name="pk_check_results"),
        ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_check_results_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        Index("ix_check_results_case_id_check_id", "case_id", "check_id"),
        Index("ix_check_results_finding_id", "finding_id"),
    )
