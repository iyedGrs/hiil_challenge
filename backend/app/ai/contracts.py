"""Strict schemas bounding every AI response (spec/backend.md B5, B6, B7).

These models are the enforcement point for the hard boundaries in B1. They are
``extra="forbid"``, which is what makes the prohibitions structural rather than
aspirational:

* **No legal reference output.** The check schema has no legal field at all, so a
  returned ``legal_reference_ids`` is an extra-field violation and the whole
  response is rejected (B5). Fixed references are attached afterwards from the
  reviewed checklist.
* **No model arithmetic.** ``monetary_facts`` entries can only carry a copied
  source string plus its provenance. There is no ``balance``, ``damages``,
  ``total_paid`` or computed-difference field to populate, so a model-derived
  balance cannot be expressed, let alone published (B6, B7, BE-07).
* **No invented checks.** ``check_id``/``subject_id`` pairs are matched against
  the instantiated set by the caller; unknown pairs are rejected (B6).
* **Three outcomes only.** ``not_applicable`` is absent from
  :class:`ModelCheckResult` because it is owned by backend code (B5, B9).

Every value here is *provisional*. Passing these schemas only proves the shape is
legal; a fact still has to match stored page text before anything that depends on
it can be published (B7).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import StrEnum

#: Version of the request/response schemas, recorded on cached extractions so a
#: schema change invalidates reuse (B6).
SCHEMA_VERSION = "s1"

#: Version of the prompt/rule set that produced a response (B6).
PROMPT_VERSION = "p1"

#: Bounds on free text coming back from a model. Short by design: explanations
#: are meant to be a sentence of justification, not a narrative.
MAX_SOURCE_TEXT = 600
#: ``value_text`` must be anchored inside ``source_text``, so it can never be
#: longer than the quote. A tighter cap made a sentence-shaped fact (e.g. a
#: ``delivery_confirmation``) reject the whole extraction response.
MAX_VALUE_TEXT = MAX_SOURCE_TEXT
MAX_EXPLANATION = 400
MAX_FACTS_PER_DOCUMENT = 60
MAX_CHECKS_PER_RUN = 60


class FactKind(StrEnum):
    """The only fact kinds an extraction may report (spec/backend.md B6).

    A closed vocabulary keeps the model from inventing a semantic role that no
    downstream rule understands. ``invoice_subtotal`` exists specifically so a
    subtotal is *distinguishable* from a total and cannot be added to it during
    reconciliation (B7: "avoid counting both subtotal and total").
    """

    invoice_number = "invoice_number"
    invoice_total = "invoice_total"
    invoice_subtotal = "invoice_subtotal"
    invoice_date = "invoice_date"
    party_name = "party_name"
    delivery_confirmation = "delivery_confirmation"
    delivery_date = "delivery_date"
    payment_amount = "payment_amount"
    payment_reference = "payment_reference"
    payment_date = "payment_date"
    credit_note_amount = "credit_note_amount"
    annex_reference = "annex_reference"
    contract_reference = "contract_reference"
    order_reference = "order_reference"


#: Fact kinds whose ``value_text`` is a monetary amount. Only these are ever
#: parsed with :func:`app.money.parse_source_amount`.
MONETARY_FACT_KINDS: frozenset[FactKind] = frozenset(
    {
        FactKind.invoice_total,
        FactKind.invoice_subtotal,
        FactKind.payment_amount,
        FactKind.credit_note_amount,
    }
)


class DocumentTypeLabel(StrEnum):
    """Closed set of document classifications (spec/backend.md B6)."""

    invoice = "invoice"
    delivery_note = "delivery_note"
    payment_receipt = "payment_receipt"
    bank_statement = "bank_statement"
    contract = "contract"
    purchase_order = "purchase_order"
    credit_note = "credit_note"
    correspondence = "correspondence"
    other = "other"


class ModelCheckResult(StrEnum):
    """The three outcomes a model may return (spec/backend.md B6, B9).

    ``not_applicable`` is deliberately absent: only backend code may publish it,
    after evaluating the checklist's application conditions (B5).
    """

    satisfied = "satisfied"
    contradicted = "contradicted"
    unassessable = "unassessable"


class ModelReasonCode(StrEnum):
    """Reason codes a model may return (spec/backend.md B6, B9).

    The absence-related codes a model may *not* choose -- ``PARTIAL_COVERAGE``,
    ``SOURCE_UNREADABLE``, ``INVALID_SOURCE``, ``NOT_APPLICABLE``,
    ``LEGAL_COVERAGE_UNAVAILABLE`` -- are backend-owned: they describe what the
    *pipeline* knows about coverage and validation, not what the model concluded.
    """

    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    CONFLICT = "CONFLICT"
    AMBIGUOUS_LINK = "AMBIGUOUS_LINK"


class StrictAiModel(BaseModel):
    """Base for AI payloads: any unexpected field rejects the whole response."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CandidateFact(StrictAiModel):
    """One candidate fact with full provenance (spec/backend.md B6).

    ``value_text`` and ``currency_text`` are *copied source strings*. Nothing here
    is a computed value, and the caller additionally requires ``value_text`` to be
    anchored inside ``source_text`` before the fact can be verified (B6, B7).
    """

    kind: FactKind
    value_text: Annotated[str, Field(min_length=1, max_length=MAX_VALUE_TEXT)]
    currency_text: Annotated[str, Field(max_length=32)] | None = None
    document_id: Annotated[str, Field(min_length=1, max_length=64)]
    #: 1-based page number, as everywhere in the contract (B9).
    page: Annotated[int, Field(ge=1)]
    source_text: Annotated[str, Field(min_length=1, max_length=MAX_SOURCE_TEXT)]


class ExtractionResponse(StrictAiModel):
    """Stage 1 output for exactly one document (spec/backend.md B6).

    ``reading_issues`` lets the model report that a page was unreadable to it.
    That is a *hint*, never the coverage manifest: the manifest is computed from
    the pipeline's own processing (B6).
    """

    document_id: Annotated[str, Field(min_length=1, max_length=64)]
    document_type: DocumentTypeLabel | None = None
    facts: Annotated[list[CandidateFact], Field(max_length=MAX_FACTS_PER_DOCUMENT)] = []
    reading_issues: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=30)] = []


class CheckJudgment(StrictAiModel):
    """One judgment for one supplied check/subject pair (spec/backend.md B6).

    ``fact_ids`` cites already-validated facts by their backend-assigned IDs;
    ``satisfied``/``contradicted`` require at least one, which the caller enforces
    (B6). ``explanation`` is short, source-based and never published as the
    finding text -- the message the preparer reads is backend-rendered.
    """

    check_id: Annotated[str, Field(min_length=1, max_length=100)]
    subject_id: Annotated[str, Field(min_length=1, max_length=64)]
    result: ModelCheckResult
    reason_code: ModelReasonCode
    fact_ids: Annotated[list[Annotated[str, Field(max_length=64)]], Field(max_length=20)] = []
    explanation: Annotated[str, Field(max_length=MAX_EXPLANATION)] = ""


class CheckResponse(StrictAiModel):
    """Stage 2 output (spec/backend.md B6).

    ``monetary_facts`` may only repeat or newly extract *source* amounts. Because
    the entry type is :class:`CandidateFact`, there is no field in which a
    computed total, difference or narrative reconciliation could be returned
    (B6, B7).
    """

    checks: Annotated[list[CheckJudgment], Field(max_length=MAX_CHECKS_PER_RUN)] = []
    monetary_facts: Annotated[list[CandidateFact], Field(max_length=MAX_FACTS_PER_DOCUMENT)] = []
