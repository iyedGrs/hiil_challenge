"""Durable job worker (spec/backend.md B8, spec/local-dev.md L4).

Run with ``python -m app.worker``. A database job table is sufficient for this
system: no broker, no Redis, no Celery (B2).

Claiming uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so several workers can run
without double-claiming, then holds a lease refreshed by a heartbeat. An expired
lease is requeued, attempts are bounded, and failures are stored sanitized: no
tracebacks, provider payloads or document content ever reach the job row
(B8, B9, spec/local-dev.md L6).

``AI_MAX_CONCURRENCY`` caps how many jobs one worker process runs at a time; the
default of 1 means one concurrent provider call (B8 rate/cost controls). A job
kind with no registered handler fails with a clear sanitized error instead of
silently succeeding.
"""

from __future__ import annotations

import logging
import os
import secrets
import signal
import socket
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import FrameType

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import session_scope
from app.domain.enums import JobKind, JobStatus
from app.errors import ApiError, sanitize_error_message
from app.ids import new_id
from app.models.job import Job

logger = logging.getLogger("app.worker")

#: How long a claimed job stays leased without a heartbeat.
LEASE_SECONDS = 60
#: Heartbeat interval; comfortably shorter than the lease.
HEARTBEAT_SECONDS = 20
#: Idle sleep between empty polls.
POLL_INTERVAL_SECONDS = 2.0
#: Backoff applied before a failed-but-retryable job becomes claimable again.
RETRY_BACKOFF_SECONDS = 15

#: Sanitized message stored when no handler is registered for a job kind.
NO_HANDLER_MESSAGE = "No handler is registered for this job kind in this build."
NO_HANDLER_CODE = "HANDLER_UNAVAILABLE"

#: A handler receives an open session and the claimed job and must not commit;
#: the loop owns the transaction boundary.
JobHandler = Callable[[DbSession, Job], None]

#: Handlers by job kind, populated by :func:`register_default_handlers`. A kind
#: with no handler fails with a sanitized error rather than silently succeeding.
HANDLERS: dict[JobKind, JobHandler] = {}


def register_handler(kind: JobKind, handler: JobHandler) -> None:
    """Register the handler for ``kind``, replacing any existing entry."""
    HANDLERS[kind] = handler


def register_default_handlers() -> None:
    """Register every shipped job handler.

    Imported inside the function so the pipeline (and therefore the AI adapter
    module) is only loaded by a process that actually runs jobs. Idempotent, so
    tests may call it freely.
    """
    from app.pipeline.analysis import handle_analysis_job

    register_handler(JobKind.analysis, handle_analysis_job)


def worker_identity() -> str:
    """Return a stable, non-secret identity for lease ownership.

    Host and PID make it readable in logs; the random suffix keeps two workers on
    one host distinct after a PID reuse.
    """
    return f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def requeue_expired_leases(db: DbSession) -> int:
    """Return running jobs whose lease expired to ``queued``.

    A crashed worker leaves a running row behind; without this the job would
    never be retried. Attempts are already counted, so the bounded-attempt
    guarantee still holds (spec/backend.md B8).
    """
    result = db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.running,
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < _now(),
        )
        .values(
            status=JobStatus.queued,
            lease_owner=None,
            lease_expires_at=None,
            available_at=_now(),
        )
    )
    return int(result.rowcount or 0)


def claim_one(db: DbSession, owner: str) -> Job | None:
    """Claim a single queued job with ``FOR UPDATE SKIP LOCKED``.

    ``SKIP LOCKED`` lets concurrent workers claim different rows instead of
    blocking on the same one. The caller owns the transaction.

    Returns:
        The claimed job with a fresh lease, or ``None`` when nothing is ready.
    """
    now = _now()
    statement = (
        select(Job)
        .where(
            Job.status == JobStatus.queued,
            (Job.available_at.is_(None)) | (Job.available_at <= now),
        )
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalar(statement)
    if job is None:
        return None

    job.status = JobStatus.running
    job.lease_owner = owner
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.heartbeat_at = now
    job.attempts = job.attempts + 1
    job.started_at = job.started_at or now
    job.error_code = None
    job.error_message = None
    db.flush()
    return job


def heartbeat(db: DbSession, job_id: str, owner: str) -> bool:
    """Extend the lease for ``job_id`` if ``owner`` still holds it.

    Returns:
        True when the lease was extended; False when the job was taken over or
        already finished, which tells the handler loop to stop.
    """
    now = _now()
    result = db.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.lease_owner == owner,
            Job.status == JobStatus.running,
        )
        .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS))
    )
    return bool(result.rowcount)


def _release_success(db: DbSession, job_id: str, owner: str) -> None:
    """Promote a still-running job to ``succeeded``.

    The ``status == running`` guard matters: a handler may legitimately end a job
    in a different terminal state -- an analysis whose case moved on sets
    ``superseded`` itself (spec/backend.md B7) -- and that decision must not be
    overwritten by the generic success path.
    """
    db.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_owner == owner, Job.status == JobStatus.running)
        .values(
            status=JobStatus.succeeded,
            phase=None,
            lease_owner=None,
            lease_expires_at=None,
            finished_at=_now(),
            error_code=None,
            error_message=None,
        )
    )


def _release_failure(
    db: DbSession,
    job_id: str,
    owner: str,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    """Fail or requeue a job with a sanitized error (spec/backend.md B8, B9)."""
    job = db.get(Job, job_id)
    if job is None:
        return
    exhausted = job.attempts >= job.max_attempts or not retryable
    job.lease_owner = None
    job.lease_expires_at = None
    job.error_code = code
    job.error_message = message[:500]
    if exhausted:
        job.status = JobStatus.failed
        job.finished_at = _now()
    else:
        # Bounded automatic retry only; a crash after a provider response makes
        # billing uncertain, so replays stay limited (spec/backend.md B8).
        job.status = JobStatus.queued
        job.available_at = _now() + timedelta(seconds=RETRY_BACKOFF_SECONDS)


class Worker:
    """Polling loop with lease heartbeats and graceful shutdown."""

    def __init__(self, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
        self.settings = get_settings()
        self.identity = worker_identity()
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._concurrency = self.settings.ai_max_concurrency

    def request_stop(self, signum: int | None = None, frame: FrameType | None = None) -> None:
        """Signal the loop to finish the current job and exit (SIGTERM/SIGINT)."""
        if not self._stop.is_set():
            logger.info("Shutdown requested (signal=%s)", signum)
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers where the platform supports them."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.request_stop)
            except (ValueError, OSError):  # pragma: no cover - non-main thread
                logger.debug("Could not install handler for signal %s", sig)

    def run(self) -> None:
        """Poll for jobs until stopped.

        ``AI_MAX_CONCURRENCY`` bounds in-flight jobs; the default of 1 keeps a
        single concurrent provider call (spec/backend.md B8).
        """
        self.install_signal_handlers()
        logger.info(
            "Worker started: identity=%s concurrency=%d ai_mode=%s",
            self.identity,
            self._concurrency,
            self.settings.ai_mode.value,
        )
        in_flight: set[Future[None]] = set()
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            while not self.stopping:
                in_flight = {future for future in in_flight if not future.done()}
                if len(in_flight) >= self._concurrency:
                    self._sleep(0.2)
                    continue

                job_id = self._claim_next()
                if job_id is None:
                    self._sleep(self.poll_interval)
                    continue

                in_flight.add(pool.submit(self._run_job, job_id))

            for future in list(in_flight):
                future.result()
        logger.info("Worker stopped: identity=%s", self.identity)

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep so SIGTERM does not wait a full poll interval."""
        self._stop.wait(timeout=seconds)

    def _claim_next(self) -> str | None:
        """Requeue expired leases and claim one job. Returns its ID."""
        try:
            with session_scope() as db:
                requeued = requeue_expired_leases(db)
                if requeued:
                    logger.info("Requeued %d job(s) with expired leases", requeued)
                job = claim_one(db, self.identity)
                return None if job is None else job.id
        except SQLAlchemyError as exc:
            # The database may be restarting; back off instead of crash-looping.
            logger.warning("Claim failed: %s", sanitize_error_message(exc))
            self._sleep(self.poll_interval)
            return None

    def _run_job(self, job_id: str) -> None:
        """Execute one job under a heartbeat, releasing it either way."""
        stop_heartbeat = threading.Event()
        beat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job_id, stop_heartbeat),
            name=f"heartbeat-{job_id}",
            daemon=True,
        )
        beat.start()
        try:
            self._execute(job_id)
        finally:
            stop_heartbeat.set()
            beat.join(timeout=5)

    def _heartbeat_loop(self, job_id: str, stop: threading.Event) -> None:
        while not stop.wait(timeout=HEARTBEAT_SECONDS):
            try:
                with session_scope() as db:
                    if not heartbeat(db, job_id, self.identity):
                        logger.warning("Lease lost for job; stopping heartbeat")
                        return
            except SQLAlchemyError as exc:
                logger.warning("Heartbeat failed: %s", sanitize_error_message(exc))

    def _execute(self, job_id: str) -> None:
        """Dispatch to the registered handler and record the outcome."""
        try:
            with session_scope() as db:
                job = db.get(Job, job_id)
                if job is None or job.lease_owner != self.identity:
                    logger.warning("Claimed job is no longer owned by this worker")
                    return
                handler = HANDLERS.get(job.kind)
                if handler is None:
                    # Not retryable: a missing handler will not appear on retry.
                    _release_failure(
                        db,
                        job_id,
                        self.identity,
                        NO_HANDLER_CODE,
                        NO_HANDLER_MESSAGE,
                        retryable=False,
                    )
                    logger.error("No handler registered for job kind %s", job.kind.value)
                    return
                handler(db, job)
                _release_success(db, job_id, self.identity)
        except ApiError as exc:
            self._fail(job_id, exc.code, sanitize_error_message(exc), exc.retryable)
        except Exception as exc:  # noqa: BLE001 - the loop must survive any handler
            logger.exception("Job failed", exc_info=exc)
            self._fail(job_id, "INTERNAL_ERROR", sanitize_error_message(exc), retryable=True)

    def _fail(self, job_id: str, code: str, message: str, retryable: bool) -> None:
        try:
            with session_scope() as db:
                _release_failure(db, job_id, self.identity, code, message, retryable)
        except SQLAlchemyError as exc:
            logger.error("Could not record job failure: %s", sanitize_error_message(exc))


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m app.worker`` (spec/local-dev.md L4)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    del argv  # no command-line options in this slice
    register_default_handlers()
    Worker().run()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
