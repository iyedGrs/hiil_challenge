"""Durable jobs, usage records and idempotency keys (spec/backend.md B8).

One durable DB job exists per revision/idempotency key. Workers claim a job with
a lease and heartbeat and bounded attempts; a crash after a provider response can
create uncertain billing, so attempts are recorded and automatic replays stay
bounded (B8).

Usage is reserved conservatively before dispatch and reconciled afterwards:
usage logging alone is not a hard cap (B8).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
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

from app.domain.enums import ExecutionMode, JobKind, JobPhase, JobStatus
from app.models.base import (
    Base,
    JsonType,
    Money,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Job(Base, TimestampMixin):
    """A leased unit of worker work (spec/backend.md B8, B9).

    ``(case_id, kind, idempotency_key)`` is unique so a repeated client request
    reuses the same job instead of launching a second provider run. ``lease_owner``
    plus ``lease_expires_at`` make an abandoned job requeueable without a broker,
    and ``input_revision`` lets a revision change mark an in-flight run
    ``superseded`` (B7).
    """

    __tablename__ = "jobs"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[JobKind] = mapped_column(enum_type(JobKind), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus), nullable=False, default=JobStatus.queued
    )
    phase: Mapped[JobPhase | None] = mapped_column(enum_type(JobPhase), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Case revision the job was created for (spec/backend.md B7, B8).
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode), nullable=False, default=ExecutionMode.fixture
    )
    #: Opaque worker identity holding the lease; null when unclaimed.
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    #: Earliest time the job may be claimed again after a bounded backoff.
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Sanitized error text only; no tracebacks, provider payloads or document
    #: content (spec/backend.md B9, spec/local-dev.md L6).
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True
    )
    result_export_id: Mapped[str | None] = mapped_column(
        ForeignKey("exports.id", ondelete="SET NULL"), nullable=True
    )
    #: Job inputs, e.g. the requested analysis ID for an export. Never secrets.
    payload: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    requested_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "case_id", "kind", "idempotency_key", name="uq_jobs_case_id_kind_idempotency_key"
        ),
        Index("ix_jobs_status_available_at", "status", "available_at"),
        Index("ix_jobs_case_id_kind_status", "case_id", "kind", "status"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
    )


class UsageRecord(Base):
    """Reserved and reconciled provider usage for one attempt (B8).

    Costs are numeric, never floats. A reservation row is written before dispatch
    and updated after the call so a crash leaves a conservative reservation
    rather than an invisible spend.
    """

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Pipeline stage, e.g. ``intake_gate``, ``extract``, ``check``.
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    actual_cost_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Set when the outcome of a call is unknown, e.g. a crash mid-response (B8).
    outcome_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_column()
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_usage_records_job_id", "job_id"),
        Index("ix_usage_records_case_id_created_at", "case_id", "created_at"),
    )


class IdempotencyKey(Base):
    """Client-supplied idempotency key for a mutating operation (B8, B9).

    ``POST /cases/{id}/analyses``, ``/exports`` and ``/submissions`` carry an
    idempotency header. Replaying the same key with the same request returns the
    original result; replaying it with a different request is a conflict, which
    is why the request fingerprint is stored.
    """

    __tablename__ = "idempotency_keys"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    #: Operation scope, e.g. ``analysis``, ``export``, ``submission``.
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    #: SHA-256 over the canonical request body; no raw body is stored.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    #: Public ID of the resource the first call produced.
    result_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        PrimaryKeyConstraint("case_id", "scope", "key", name="pk_idempotency_keys"),
        Index("ix_idempotency_keys_job_id", "job_id"),
    )
