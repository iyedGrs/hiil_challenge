"""Case-scoped authorization and revision helpers (spec/backend.md B8, B9).

Shared by every case route so the ownership rule and the optimistic-concurrency
rule are written once:

* An unknown case, a case owned by somebody else and an inaccessible child
  resource all answer **404**, never 403, so case IDs cannot be probed (B9).
* A stale ``expected_revision`` answers **409 REVISION_CONFLICT**, checked while
  holding a row lock on the case so the check and the following bump are atomic
  (B9: "reject stale expected revisions atomically"). Client timestamps are never
  used as version tokens.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.errors import REVISION_CONFLICT, ApiError, not_found
from app.models.case import Case, ClaimRevision
from app.models.document import Document
from app.models.user import User


def load_owned_case(db: DbSession, case_id: str, user: User, *, lock: bool = False) -> Case:
    """Return the case owned by ``user``, or raise 404 without disclosing it.

    Args:
        db: Open session inside the request transaction.
        case_id: Public case ID from the route.
        user: Signed-in preparer.
        lock: Take ``SELECT ... FOR UPDATE`` so a revision check and the
            subsequent increment cannot interleave with another request.
    """
    statement = select(Case).where(Case.id == case_id)
    if lock:
        statement = statement.with_for_update()
    case = db.scalar(statement)
    if case is None or case.owner_id != user.id:
        raise not_found()
    return case


def require_matching_revision(case: Case, expected_revision: int) -> None:
    """Raise 409 ``REVISION_CONFLICT`` when ``expected_revision`` is stale (B9)."""
    if case.revision != expected_revision:
        raise ApiError(
            REVISION_CONFLICT,
            "The case has changed since this revision was read. Reload and review again.",
        )


def current_claim_revision(db: DbSession, case: Case) -> ClaimRevision:
    """Return the claim revision matching ``case.revision``.

    Falls back to the newest stored revision when no row carries exactly the
    case's revision number, which happens after a document upload or a finding
    response bumps the case revision without writing a new claim.
    """
    exact = db.get(ClaimRevision, (case.id, case.revision))
    if exact is not None:
        return exact
    latest = db.scalar(
        select(ClaimRevision)
        .where(ClaimRevision.case_id == case.id)
        .order_by(ClaimRevision.revision.desc())
        .limit(1)
    )
    if latest is None:  # pragma: no cover - a case always has its first revision
        raise not_found()
    return latest


def active_documents(db: DbSession, case_id: str) -> list[Document]:
    """Return the working set of documents, newest last (spec/backend.md B4).

    Rejected and detached rows are included so the UI can show that a file was
    refused or removed rather than silently losing it; ``active``/``state`` on
    the projected object distinguish them (B4, frontend.md F4).
    """
    return list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case_id)
            .order_by(Document.created_at, Document.id)
        ).all()
    )


def load_owned_document(db: DbSession, document_id: str, user: User) -> Document:
    """Return ``document_id`` when its case is owned by ``user``, else 404 (B9)."""
    document = db.scalar(
        select(Document)
        .join(Case, Case.id == Document.case_id)
        .where(Document.id == document_id, Case.owner_id == user.id)
    )
    if document is None:
        raise not_found()
    return document


def load_accessible_document(db: DbSession, document_id: str, user: User) -> Document:
    """Return ``document_id`` if ``user`` may read it, else 404 (spec/backend.md B10).

    Two authorized paths, and no others:

    * the signed-in **preparer owns the case** the document belongs to;
    * the signed-in **reviewer received a submission** that froze this document.

    The second path is what "submitted originals remain accessible only through
    authorized snapshot access" means in practice (B10): a reviewer can open the
    evidence they were sent, and nothing else. Access to one submission grants no
    access to drafts, to later revisions, or to any other case.
    """
    from app.domain.enums import Role
    from app.models.submission import Submission, SubmissionDocument

    if user.role is Role.reviewer:
        document = db.scalar(
            select(Document)
            .join(SubmissionDocument, SubmissionDocument.document_id == Document.id)
            .join(Submission, Submission.id == SubmissionDocument.submission_id)
            .where(Document.id == document_id, Submission.reviewer_id == user.id)
        )
        if document is None:
            raise not_found()
        return document

    return load_owned_document(db, document_id, user)
