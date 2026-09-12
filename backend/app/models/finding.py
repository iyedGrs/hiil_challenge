"""Findings and preparer responses (spec/backend.md B6, B7, B9).

Finding identity is ``(case_id, check_id, subject_id)`` and is enforced by a
unique constraint, so reassessment preserves identity instead of creating a new
finding per run (B7). Responses are kept with the finding *and* the revision and
analysis they were written against, so an edit never rewrites history (B7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    CheckResult,
    Delta,
    FindingStatus,
    ReasonCode,
    ResponseAction,
)
from app.models.base import (
    Base,
    JsonType,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Finding(Base, TimestampMixin):
    """A durable issue for one check/subject pair (spec/backend.md B7, B9).

    ``status`` is ``open``/``resolved``; a subject that disappears is marked
    ``not_applicable`` through its latest check result and is never reported as
    resolved by evidence (B7).
    """

    __tablename__ = "findings"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[FindingStatus] = mapped_column(
        enum_type(FindingStatus), nullable=False, default=FindingStatus.open
    )
    last_result: Mapped[CheckResult | None] = mapped_column(enum_type(CheckResult), nullable=True)
    last_reason_code: Mapped[ReasonCode | None] = mapped_column(
        enum_type(ReasonCode), nullable=True
    )
    last_delta: Mapped[Delta | None] = mapped_column(enum_type(Delta), nullable=True)
    first_seen_analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    responses: Mapped[list["FindingResponse"]] = relationship(
        back_populates="finding", order_by="FindingResponse.created_at"
    )

    __table_args__ = (
        UniqueConstraint(
            "case_id", "check_id", "subject_id", name="uq_findings_case_id_check_id_subject_id"
        ),
        ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_findings_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        Index("ix_findings_case_id_status", "case_id", "status"),
    )


class FindingResponse(Base):
    """A preparer response recorded against one finding version (B7, B9).

    ``document_ids`` lists supporting evidence the preparer attached. The stored
    ``revision`` and ``analysis_id`` pin the response to the version it answered,
    which keeps prior submissions truthful after later edits (B7, B10).
    """

    __tablename__ = "finding_responses"

    id: Mapped[str] = id_column()
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    #: Case revision produced by saving this response (spec/backend.md B9).
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[ResponseAction] = mapped_column(enum_type(ResponseAction), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    finding: Mapped[Finding] = relationship(back_populates="responses")

    __table_args__ = (
        Index("ix_finding_responses_finding_id", "finding_id"),
        Index("ix_finding_responses_case_id_revision", "case_id", "revision"),
    )
