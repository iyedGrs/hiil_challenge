"""SQLAlchemy models for every entity in the persistence table (B8).

Importing this package registers every mapped class on ``Base.metadata``, which
is what ``migrations/env.py`` and ``Base.metadata.create_all`` rely on. Add new
model modules to the imports below or Alembic will not see their tables.
"""

from __future__ import annotations

from app.models.analysis import Analysis, CheckResultRow
from app.models.base import Base, Money, utcnow
from app.models.case import Case, ClaimRevision
from app.models.document import Document, Page
from app.models.fact import Extraction, Fact
from app.models.finding import Finding, FindingResponse
from app.models.job import IdempotencyKey, Job, UsageRecord
from app.models.legal import Check, LegalPack, LegalReference
from app.models.subject import Subject
from app.models.submission import (
    Export,
    ReviewEvent,
    Submission,
    SubmissionDocument,
)
from app.models.user import Recipient, Session, User

#: Metadata handed to Alembic (``migrations/env.py``).
metadata = Base.metadata

__all__ = [
    "Analysis",
    "Base",
    "Case",
    "Check",
    "CheckResultRow",
    "ClaimRevision",
    "Document",
    "Export",
    "Extraction",
    "Fact",
    "Finding",
    "FindingResponse",
    "IdempotencyKey",
    "Job",
    "LegalPack",
    "LegalReference",
    "Money",
    "Page",
    "Recipient",
    "ReviewEvent",
    "Session",
    "Subject",
    "Submission",
    "SubmissionDocument",
    "UsageRecord",
    "User",
    "metadata",
    "utcnow",
]
