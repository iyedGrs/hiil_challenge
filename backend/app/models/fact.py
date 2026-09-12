"""Extraction runs and candidate facts (spec/backend.md B6, B7, B8).

Facts are backend-owned records of *copied source strings*. ``value_text`` and
``currency_text`` are literal source text; ``normalized_value`` is filled only
when the numeric token's locale/format is unambiguous, otherwise it stays null
and the dependent check is unassessable (B7).

Verification state is stored separately from parsing and semantic judgment: a
failed quote match quarantines the fact so dependent judgments cannot be
published as supported (B7).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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

from app.domain.enums import ExecutionMode, FactVerification, ReasonCode
from app.models.base import (
    Base,
    JsonType,
    Money,
    created_at_column,
    enum_type,
    id_column,
)


class Extraction(Base):
    """One cached Stage 1 extraction over one document (spec/backend.md B6).

    The primary key is the deterministic cache key over owner/case scope,
    document hash, page-text extraction version, schema/prompt version and model
    configuration, so an unchanged document reuses validated facts and no cache
    is shared across cases. This row is internal and is not addressed by any
    route, so it carries no public opaque ID.
    """

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode), nullable=False
    )
    #: Counts and reading issues; never raw model output (spec/backend.md B6).
    summary: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejected_fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_column()

    facts: Mapped[list["Fact"]] = relationship(back_populates="extraction")

    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "document_sha256",
            "extraction_version",
            "schema_version",
            "prompt_version",
            "model_version",
            name="uq_extractions_cache_key",
        ),
        Index("ix_extractions_document_id", "document_id"),
    )


class Fact(Base):
    """A validated or quarantined candidate fact (spec/backend.md B6, B7).

    Every document-derived fact carries ``{document_id, page, source_text}``;
    the quote must be located in the stored page text under the recorded
    normalization version before it can support a published judgment.
    """

    __tablename__ = "facts"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    extraction_id: Mapped[str | None] = mapped_column(
        ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Filled only for unambiguous numeric tokens; never a computed total (B7).
    normalized_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    verification: Mapped[FactVerification] = mapped_column(
        enum_type(FactVerification), nullable=False, default=FactVerification.pending
    )
    #: Reason a fact was quarantined, e.g. ``INVALID_SOURCE`` (B9).
    quarantine_reason: Mapped[ReasonCode | None] = mapped_column(
        enum_type(ReasonCode), nullable=True
    )
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Case-scoped subject this fact belongs to, once linkage is unambiguous.
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extraction: Mapped[Extraction | None] = relationship(back_populates="facts")

    __table_args__ = (
        # RESTRICT, not SET NULL: subjects are retained across revisions rather
        # than deleted (spec/backend.md B7), and case_id is NOT NULL.
        ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_facts_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        Index("ix_facts_case_id_verification", "case_id", "verification"),
        Index("ix_facts_document_id_page", "document_id", "page"),
        Index("ix_facts_case_id_subject_id", "case_id", "subject_id"),
    )
