"""Stable case-scoped subjects (spec/backend.md B6, B7).

Subjects are created by backend code, never minted by the model, and they
persist through case revisions and same-subject replacements so finding identity
``(case_id, check_id, subject_id)`` stays stable (B7).

When identity or linkage is ambiguous the subject is preserved unlinked with
``linkage_confirmed=False`` and a clarification question is raised, rather than
merging parties or invoices on a matching amount alone (B6, B7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import SubjectType
from app.models.base import Base, JsonType, TimestampMixin, enum_type


class Subject(Base, TimestampMixin):
    """A transaction, invoice, payment, credit note or referenced annex (B6).

    The primary key is ``(case_id, subject_id)`` because subject IDs are
    human-readable and case-scoped (``invoice_0001``), unlike the opaque global
    IDs used elsewhere. ``sequence`` is allocated per ``(case_id, subject_type)``
    by :func:`app.ids.next_subject_id` and is never reused inside a case.
    """

    __tablename__ = "subjects"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[SubjectType] = mapped_column(enum_type(SubjectType), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Confirmed external identifiers, e.g. an invoice number found in sources.
    identifiers: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    #: Parent subject, e.g. a payment linked to an invoice. Never inferred from a
    #: matching amount alone (spec/backend.md B7).
    linked_subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linkage_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Set by a preparer confirmation rather than model output, when applicable.
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    #: False when the subject no longer exists in the working case. History is
    #: retained and its checks become ``not_applicable``, never "resolved" (B7).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("case_id", "subject_id", name="pk_subjects"),
        UniqueConstraint(
            "case_id",
            "subject_type",
            "sequence",
            name="uq_subjects_case_id_subject_type_sequence",
        ),
        Index("ix_subjects_case_id_subject_type", "case_id", "subject_type"),
    )
