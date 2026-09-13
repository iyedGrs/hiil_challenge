"""Stage 1 extraction, caching and source validation (spec/backend.md B6, B7).

This module is the gate every candidate fact must pass before anything may depend
on it. A candidate becomes ``verified`` only when all of the following hold:

1. it names the document actually being extracted, which belongs to the analysed
   snapshot;
2. the cited page exists in that document's page registry and is readable;
3. its ``source_text`` occurs in the stored page text under the versioned
   normalization policy -- exact containment, never fuzzy (B7);
4. its ``value_text`` occurs inside its own ``source_text``, so a real but
   irrelevant quote cannot smuggle in an unrelated amount (B6).

Anything else is stored ``quarantined`` with ``INVALID_SOURCE`` rather than
dropped, so ``coverage.rejected_facts`` reports a real number and a reviewer can
see that output was discarded (B7, BE-04).

Monetary values get a ``normalized_value`` only when :func:`parse_source_amount`
can resolve the token unambiguously. An ambiguous token keeps its literal text and
a null normalized value, which later makes the dependent check unassessable
instead of guessing (B7, BE-06).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ai.base import AiAdapter, DocumentInput, PageInput
from app.ai.contracts import (
    MONETARY_FACT_KINDS,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    CandidateFact,
    FactKind,
)
from app.domain.enums import ExecutionMode, FactVerification, PageState, ReasonCode
from app.extraction import EXTRACTION_VERSION
from app.ids import FACT_PREFIX, new_id
from app.models.base import utcnow
from app.models.document import Document, Page
from app.models.fact import Extraction, Fact
from app.money import parse_source_amount
from app.normalization import (
    NORMALIZATION_VERSION,
    quote_matches_page,
    value_anchored_in_quote,
)

logger = logging.getLogger("app.pipeline.facts")


@dataclass
class ExtractionOutcome:
    """Result of extracting one document."""

    extraction: Extraction
    verified: list[Fact] = field(default_factory=list)
    quarantined: list[Fact] = field(default_factory=list)
    reused_from_cache: bool = False

    @property
    def rejected_count(self) -> int:
        return len(self.quarantined)


def cache_key(
    *,
    case_id: str,
    document_sha256: str,
    model_version: str,
) -> str:
    """Return the deterministic Stage 1 cache key (spec/backend.md B6).

    Scoped by case *and* document hash, plus every version that can change the
    meaning of the output: page-text extraction, schema, prompt and model
    configuration. Case scoping is deliberate -- there is no global cross-customer
    cache (B6).
    """
    material = "|".join(
        [
            case_id,
            document_sha256,
            EXTRACTION_VERSION,
            SCHEMA_VERSION,
            PROMPT_VERSION,
            model_version,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def document_input(document: Document, pages: list[Page]) -> DocumentInput:
    """Build the adapter payload for one document (spec/backend.md B6)."""
    return DocumentInput(
        document_id=document.id,
        filename=document.display_name,
        mime_type=document.mime_type,
        pages=tuple(
            PageInput(
                page=page.page_number,
                text=page.text,
                method=page.method.value,
                state=page.state.value,
            )
            for page in pages
        ),
    )


def _validate_candidate(
    candidate: CandidateFact,
    document: Document,
    pages_by_number: dict[int, Page],
) -> tuple[bool, ReasonCode | None]:
    """Return ``(is_valid, quarantine_reason)`` for one candidate (B7).

    Kept separate from persistence so the rule set is readable on its own and can
    be unit-tested without a database.
    """
    if candidate.document_id != document.id:
        return False, ReasonCode.INVALID_SOURCE

    page = pages_by_number.get(candidate.page)
    if page is None:
        return False, ReasonCode.INVALID_SOURCE
    if page.state is PageState.unreadable:
        # Nothing can be quoted from a page with no usable stored text.
        return False, ReasonCode.SOURCE_UNREADABLE
    if not quote_matches_page(candidate.source_text, page.text):
        return False, ReasonCode.INVALID_SOURCE
    if not value_anchored_in_quote(candidate.value_text, candidate.source_text):
        return False, ReasonCode.INVALID_SOURCE
    return True, None


def _persist_fact(
    db: DbSession,
    *,
    case_id: str,
    extraction: Extraction,
    candidate: CandidateFact,
    verification: FactVerification,
    quarantine_reason: ReasonCode | None,
    model_version: str,
) -> Fact:
    """Insert one fact row with its provenance and verification state (B7)."""
    normalized = None
    if candidate.kind in MONETARY_FACT_KINDS and verification is FactVerification.verified:
        # None here means "the token is ambiguous", which is a legitimate,
        # recorded outcome -- not a validation failure (B7).
        normalized = parse_source_amount(candidate.value_text)

    row = Fact(
        id=new_id(FACT_PREFIX),
        case_id=case_id,
        extraction_id=extraction.id,
        kind=candidate.kind.value,
        value_text=candidate.value_text,
        currency_text=candidate.currency_text,
        normalized_value=normalized,
        document_id=candidate.document_id,
        page=candidate.page,
        source_text=candidate.source_text,
        verification=verification,
        quarantine_reason=quarantine_reason,
        extraction_version=EXTRACTION_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        model_version=model_version,
        verified_at=utcnow() if verification is FactVerification.verified else None,
    )
    db.add(row)
    return row


def extract_document(
    db: DbSession,
    *,
    case_id: str,
    document: Document,
    pages: list[Page],
    adapter: AiAdapter,
) -> ExtractionOutcome:
    """Extract and validate one document, reusing a cached run when possible.

    An unchanged document reuses its validated facts rather than paying for a
    second provider call (B6, BE-11). The cache is keyed by content hash, so
    re-uploading the same bytes under a new name also hits it.
    """
    key = cache_key(
        case_id=case_id,
        document_sha256=document.sha256,
        model_version=adapter.model_version,
    )
    cached = db.get(Extraction, key)
    if cached is not None:
        facts = list(db.scalars(select(Fact).where(Fact.extraction_id == key)).all())
        logger.info(
            "Reusing cached extraction: document=%s facts=%d", document.id, len(facts)
        )
        return ExtractionOutcome(
            extraction=cached,
            verified=[f for f in facts if f.verification is FactVerification.verified],
            quarantined=[f for f in facts if f.verification is FactVerification.quarantined],
            reused_from_cache=True,
        )

    response = adapter.extract_facts(document_input(document, pages))

    extraction = Extraction(
        id=key,
        case_id=case_id,
        document_id=document.id,
        document_sha256=document.sha256,
        extraction_version=EXTRACTION_VERSION,
        schema_version=SCHEMA_VERSION,
        prompt_version=PROMPT_VERSION,
        model_version=adapter.model_version,
        execution_mode=ExecutionMode(adapter.execution_mode),
        document_type=response.document_type.value if response.document_type else None,
        summary={
            "candidate_count": len(response.facts),
            "reading_issues": list(response.reading_issues),
        },
    )
    db.add(extraction)
    db.flush()

    pages_by_number = {page.page_number: page for page in pages}
    outcome = ExtractionOutcome(extraction=extraction)
    for candidate in response.facts:
        valid, reason = _validate_candidate(candidate, document, pages_by_number)
        row = _persist_fact(
            db,
            case_id=case_id,
            extraction=extraction,
            candidate=candidate,
            verification=FactVerification.verified if valid else FactVerification.quarantined,
            quarantine_reason=reason,
            model_version=adapter.model_version,
        )
        (outcome.verified if valid else outcome.quarantined).append(row)

    extraction.rejected_fact_count = len(outcome.quarantined)
    db.flush()
    logger.info(
        "Extracted document=%s type=%s verified=%d quarantined=%d",
        document.id,
        extraction.document_type,
        len(outcome.verified),
        len(outcome.quarantined),
    )
    return outcome


def validate_stage2_facts(
    db: DbSession,
    *,
    case_id: str,
    extraction: Extraction,
    candidates: list[CandidateFact],
    documents_by_id: dict[str, Document],
    pages_by_document: dict[str, dict[int, Page]],
    existing: list[Fact],
    adapter: AiAdapter,
) -> tuple[list[Fact], list[Fact]]:
    """Validate monetary facts returned by Stage 2 (spec/backend.md B6).

    New candidates must carry full provenance and pass exactly the same gate as
    Stage 1; a duplicate of an existing fact reuses that fact's ID instead of
    creating a second row.

    Returns:
        ``(verified, quarantined)`` for the newly created rows only.
    """
    by_identity = {
        (fact.kind, fact.value_text, fact.document_id, fact.page, fact.source_text): fact
        for fact in existing
    }
    verified: list[Fact] = []
    quarantined: list[Fact] = []

    for candidate in candidates:
        identity = (
            candidate.kind.value,
            candidate.value_text,
            candidate.document_id,
            candidate.page,
            candidate.source_text,
        )
        if identity in by_identity:
            continue

        document = documents_by_id.get(candidate.document_id)
        if document is None:
            # A document outside the analysed snapshot cannot be cited at all.
            quarantined.append(
                _persist_fact(
                    db,
                    case_id=case_id,
                    extraction=extraction,
                    candidate=candidate,
                    verification=FactVerification.quarantined,
                    quarantine_reason=ReasonCode.INVALID_SOURCE,
                    model_version=adapter.model_version,
                )
            )
            continue

        valid, reason = _validate_candidate(
            candidate, document, pages_by_document.get(candidate.document_id, {})
        )
        row = _persist_fact(
            db,
            case_id=case_id,
            extraction=extraction,
            candidate=candidate,
            verification=FactVerification.verified if valid else FactVerification.quarantined,
            quarantine_reason=reason,
            model_version=adapter.model_version,
        )
        (verified if valid else quarantined).append(row)

    db.flush()
    return verified, quarantined


def facts_by_kind(facts: list[Fact]) -> dict[str, list[Fact]]:
    """Group facts by their ``kind`` for rule lookups."""
    grouped: dict[str, list[Fact]] = {}
    for fact in facts:
        grouped.setdefault(fact.kind, []).append(fact)
    return grouped


def is_monetary(kind: str) -> bool:
    """Return True when ``kind`` names a monetary fact."""
    try:
        return FactKind(kind) in MONETARY_FACT_KINDS
    except ValueError:
        return False
