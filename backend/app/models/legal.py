"""Legal pack, references and checklist definitions (spec/backend.md B5).

Packs are versioned JSON assets loaded into these tables at startup; no vector
search is needed for a bounded pack. Lawyer-authored ``legal_reference_ids`` on a
check are immutable inputs to publication: the model has no legal-reference
output field, and any returned legal ID is an extra-field violation (B5).

Unknown effective dates stay unknown. Nothing here may be labelled
"lawyer-reviewed" unless a real review was recorded.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import CaseType, LegalCoverage, SubjectType
from app.models.base import Base, JsonType, TimestampMixin, enum_type


class LegalPack(Base, TimestampMixin):
    """A versioned checklist/reference bundle (spec/backend.md B5).

    The backend maps a confirmed ``case_type`` to a fixed pack version; the model
    never selects packs or provisions. ``coverage`` records whether a validated
    pack backs it, and ``unvalidated`` must stay disclosed downstream (B5, B10).
    """

    __tablename__ = "legal_packs"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_type: Mapped[CaseType] = mapped_column(enum_type(CaseType), nullable=False)
    coverage: Mapped[LegalCoverage] = mapped_column(
        enum_type(LegalCoverage), nullable=False, default=LegalCoverage.unvalidated
    )
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    #: Human-readable provenance of the asset; not a certification.
    source_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    asset_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Review labels and disclosure strings shipped with the pack.
    labels: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)

    __table_args__ = (Index("ix_legal_packs_case_type", "case_type"),)


class LegalReference(Base):
    """One legal reference inside a pack version (spec/backend.md B5).

    Effective dates are nullable on purpose: an unknown effective date must
    remain unknown rather than be guessed.
    """

    __tablename__ = "legal_references"

    pack_version: Mapped[str] = mapped_column(
        ForeignKey("legal_packs.version", ondelete="RESTRICT"), nullable=False
    )
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    code_article: Mapped[str] = mapped_column(String(200), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_page: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(nullable=True)
    effective_to: Mapped[date | None] = mapped_column(nullable=True)
    conditions: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    exceptions: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    related_reference_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("pack_version", "reference_id", name="pk_legal_references"),
    )


class Check(Base):
    """A checklist definition instantiated against subjects (spec/backend.md B5).

    ``applies_when`` holds backend-evaluated conditions (tri-state: applies, does
    not apply, unknown) and ``satisfied_by`` encodes acceptable alternative
    evidence, so equivalent proof is not rejected by a fixed filename list.
    """

    __tablename__ = "checks"

    pack_version: Mapped[str] = mapped_column(
        ForeignKey("legal_packs.version", ondelete="RESTRICT"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    #: ``checklist`` / ``evidence_guidance`` / ``reconciliation`` etc. Contract
    #: requirements and evidence recommendations are not relabelled as law (B5).
    basis: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_reference_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    applies_when: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    subject_type: Mapped[SubjectType] = mapped_column(enum_type(SubjectType), nullable=False)
    satisfied_by: Mapped[list[dict[str, object]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    #: Preparer actions offered for an open finding on this check (B9).
    actions: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        PrimaryKeyConstraint("pack_version", "check_id", name="pk_checks"),
        Index("ix_checks_pack_version_subject_type", "pack_version", "subject_type"),
    )
