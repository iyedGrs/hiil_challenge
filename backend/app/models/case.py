"""Cases and claim revisions (spec/backend.md B3, B7, B8, B9).

``cases.revision`` is the optimistic-concurrency token: mutations carry
``expected_revision`` and are rejected atomically when stale (B9). Each revision
of the typed claim is stored, and the cheap-gate result is cached on the revision
it was computed for, so an unchanged claim revision reuses its gate result (B3).

Typed claim data has ``origin=user_claim`` with a field path and revision; it is
not a document-derived fact and never receives document/page provenance (B3).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    CaseType,
    ClaimOrigin,
    Currency,
    IntakeStatus,
    RequestedOutcome,
)
from app.models.base import (
    Base,
    JsonType,
    Money,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Case(Base, TimestampMixin):
    """Working case owned by exactly one preparer (spec/backend.md B2, B8).

    ``revision`` increments when the claim, active documents or finding
    responses change (B9). The current claim is the :class:`ClaimRevision` whose
    ``revision`` equals this value; ``intake_status`` mirrors that revision's
    cached gate result for cheap list rendering.
    """

    __tablename__ = "cases"

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    case_type: Mapped[CaseType] = mapped_column(enum_type(CaseType), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intake_status: Mapped[IntakeStatus] = mapped_column(
        enum_type(IntakeStatus), nullable=False, default=IntakeStatus.not_checked
    )
    reference_label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    claim_revisions: Mapped[list["ClaimRevision"]] = relationship(
        back_populates="case", order_by="ClaimRevision.revision"
    )

    __table_args__ = (
        Index("ix_cases_owner_id", "owner_id"),
        Index("ix_cases_owner_id_updated_at", "owner_id", "updated_at"),
    )


class ClaimRevision(Base):
    """Immutable snapshot of the structured claim at one revision (B3, B8).

    Typed columns are authoritative for reconciliation and querying;
    ``claim_json`` keeps the exact canonical object the API echoes back so an
    export or submission can reproduce it byte-for-byte. ``claimed_amount`` is a
    numeric column, never a float (B7).
    """

    __tablename__ = "claim_revisions"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    case_type: Mapped[CaseType] = mapped_column(enum_type(CaseType), nullable=False)
    claimant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    claimed_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[Currency] = mapped_column(enum_type(Currency), nullable=False)
    requested_outcome: Mapped[RequestedOutcome] = mapped_column(
        enum_type(RequestedOutcome), nullable=False
    )
    narrative: Mapped[str] = mapped_column(Text, nullable=False)

    # Explicit date keys; null means not known (spec/backend.md B3, B9).
    date_contract: Mapped[date | None] = mapped_column(nullable=True)
    date_delivery: Mapped[date | None] = mapped_column(nullable=True)
    date_invoice: Mapped[date | None] = mapped_column(nullable=True)
    date_payment_due: Mapped[date | None] = mapped_column(nullable=True)

    follow_up_answers: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    claim_json: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    origin: Mapped[ClaimOrigin] = mapped_column(
        enum_type(ClaimOrigin), nullable=False, default=ClaimOrigin.user_claim
    )

    # Cached cheap-gate result for this exact revision (spec/backend.md B3).
    intake_status: Mapped[IntakeStatus] = mapped_column(
        enum_type(IntakeStatus), nullable=False, default=IntakeStatus.not_checked
    )
    intake_questions: Mapped[list[dict[str, str]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    intake_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    intake_gate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    case: Mapped[Case] = relationship(back_populates="claim_revisions")

    __table_args__ = (
        PrimaryKeyConstraint("case_id", "revision", name="pk_claim_revisions"),
        Index("ix_claim_revisions_case_id", "case_id"),
    )
