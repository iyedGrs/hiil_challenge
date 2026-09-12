"""Exports, submissions and reviewer events (spec/backend.md B9, B10).

A submission freezes the claim revision, document hashes/IDs, checklist version,
published run, preparer responses, recipient and timestamp. Explicit submission
is the only path to reviewer access, and reviewer access to one submission grants
nothing else (B10).

Snapshot rows are copies on purpose: detaching a file from the working case must
not destroy a submitted version (B10).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ExportState, ReviewEventType, SubmissionState
from app.models.base import (
    Base,
    JsonType,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Export(Base, TimestampMixin):
    """A generated ZIP package for a published analysis (spec/backend.md B10).

    A current published assessment is required; ``partial`` is allowed only with
    explicit acknowledgement and with all limitations included in the package.
    """

    __tablename__ = "exports"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[ExportState] = mapped_column(
        enum_type(ExportState), nullable=False, default=ExportState.generating
    )
    acknowledge_unresolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Contents index: summary, evidence index, originals, checks, disclosures.
    manifest: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Sanitized failure reason; never a traceback or document content (B9).
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_exports_case_id_created_at", "case_id", "created_at"),
        Index("ix_exports_analysis_id", "analysis_id"),
    )


class Submission(Base, TimestampMixin):
    """An immutable handoff of one published run to one reviewer (B10).

    ``manifest`` and ``claim_snapshot`` freeze what the reviewer sees. Received
    and reviewed states record reviewer activity only; they do not indicate legal
    acceptance.
    """

    __tablename__ = "submissions"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_id: Mapped[str] = mapped_column(
        ForeignKey("recipients.id", ondelete="RESTRICT"), nullable=False
    )
    #: Resolved reviewer account, so reviewer queries never rescan recipients.
    reviewer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    preparer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    checklist_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[SubmissionState] = mapped_column(
        enum_type(SubmissionState), nullable=False, default=SubmissionState.submitted
    )
    acknowledge_unresolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    claim_snapshot: Mapped[dict[str, object]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    #: Frozen copies of preparer responses at submission time (B10).
    response_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    export_id: Mapped[str | None] = mapped_column(
        ForeignKey("exports.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime] = created_at_column()
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["SubmissionDocument"]] = relationship(
        back_populates="submission", order_by="SubmissionDocument.sort_order"
    )
    events: Mapped[list["ReviewEvent"]] = relationship(
        back_populates="submission", order_by="ReviewEvent.created_at"
    )

    __table_args__ = (
        Index("ix_submissions_reviewer_id_submitted_at", "reviewer_id", "submitted_at"),
        Index("ix_submissions_case_id_submitted_at", "case_id", "submitted_at"),
    )


class SubmissionDocument(Base):
    """Frozen document entry inside a submission manifest (spec/backend.md B10).

    Name, hash, size and storage key are copied at submission time so a later
    detach cannot change or destroy what a reviewer received.
    """

    __tablename__ = "submission_documents"

    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    submission: Mapped[Submission] = relationship(back_populates="documents")

    __table_args__ = (
        PrimaryKeyConstraint("submission_id", "document_id", name="pk_submission_documents"),
        Index("ix_submission_documents_document_id", "document_id"),
    )


class ReviewEvent(Base):
    """A reviewer action on a submission (spec/backend.md B9, B10).

    A clarification request is an event; the preparer then edits the working
    revision, reassesses and submits a new version.
    """

    __tablename__ = "review_events"

    id: Mapped[str] = id_column()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[ReviewEventType] = mapped_column(enum_type(ReviewEventType), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    submission: Mapped[Submission] = relationship(back_populates="events")

    __table_args__ = (Index("ix_review_events_submission_id_created_at", "submission_id", "created_at"),)
