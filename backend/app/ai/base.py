"""AI adapter interface and request payloads (spec/backend.md B6).

The pipeline talks to exactly one interface, :class:`AiAdapter`, with two
methods matching the two bounded stages. Adapters have no tools, no network
actions beyond the single provider call, no code execution, no submission
capability and no ability to alter trusted checklist data (B6).

Request payloads carry backend-owned IDs only. Document and narrative content is
passed as explicitly delimited untrusted data; instruction/data separation is
preserved, and delimiting alone is never treated as a security guarantee (B6,
BE-15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.ai.contracts import CheckResponse, ExtractionResponse


class AiUnavailableError(RuntimeError):
    """Raised when the configured provider could not be reached or answered.

    Surfaced as ``PROVIDER_UNAVAILABLE`` (503, retryable). A failure here must
    never be replaced by fixture output: L3 forbids silently switching to fixture
    results after a live provider failure.
    """


class AiResponseInvalidError(RuntimeError):
    """Raised when a provider response fails the strict schema (B6, BE-13).

    Kept distinct from :class:`AiUnavailableError` because an invalid response is
    not usefully retryable in the same way, and because invalid output must never
    become an empty success (B7).
    """


@dataclass(frozen=True)
class PageInput:
    """One page handed to an adapter (spec/backend.md B4, B6)."""

    page: int
    text: str
    method: str
    #: ``ready``/``partial``/``unreadable``. An unreadable page is still listed so
    #: the model can report reduced coverage rather than assume completeness.
    state: str


@dataclass(frozen=True)
class DocumentInput:
    """One document and its page registry (spec/backend.md B6)."""

    document_id: str
    filename: str
    mime_type: str
    pages: tuple[PageInput, ...]


@dataclass(frozen=True)
class ClaimInput:
    """The structured claim, as untrusted preparer-asserted data (B3, B6)."""

    case_type: str
    claimant_name: str
    counterparty_name: str
    claimed_amount: str
    currency: str
    requested_outcome: str
    narrative: str
    dates: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidatedFactInput:
    """A backend-validated fact offered to Stage 2 for citation (B6).

    Only verified facts appear here, and they are addressed by their stable
    backend ``fact_id``; a Stage 2 judgment cites these IDs rather than re-quoting
    text.
    """

    fact_id: str
    kind: str
    value_text: str | None
    currency_text: str | None
    document_id: str
    page: int
    source_text: str
    subject_id: str | None


@dataclass(frozen=True)
class CheckInstanceInput:
    """One instantiated check the model is asked to judge (spec/backend.md B5, B6).

    Only checks the backend has already found *eligible* are included, and the
    payload carries no legal reference: the model never sees, selects or returns
    one (B5).
    """

    check_id: str
    subject_id: str
    subject_type: str
    subject_label: str
    label: str
    #: Acceptable alternative evidence definitions from the reviewed checklist, so
    #: equivalent proof is not rejected for having the wrong document label (B5).
    satisfied_by: tuple[dict[str, object], ...]
    #: The preparer's own explanation for this finding, when one was recorded.
    preparer_explanation: str | None = None


@dataclass(frozen=True)
class CheckRequest:
    """Full Stage 2 input (spec/backend.md B6).

    Carries the claim, every readable page of the case (a bounded context, not
    summaries), the validated facts and the instantiated checks.
    """

    claim: ClaimInput
    documents: tuple[DocumentInput, ...]
    facts: tuple[ValidatedFactInput, ...]
    checks: tuple[CheckInstanceInput, ...]


class AiAdapter(Protocol):
    """Two bounded tasks over one configured model (spec/backend.md B6)."""

    #: Identifies the model/configuration in stored provenance (B6, B7).
    model_version: str
    #: ``fixture`` or ``live``; published on every run so the UI can label it (B9).
    execution_mode: str

    def extract_facts(self, document: DocumentInput) -> ExtractionResponse:
        """Stage 1: return candidate facts for one document.

        Raises:
            AiUnavailableError: the provider could not be reached.
            AiResponseInvalidError: the response failed the strict schema.
        """
        ...

    def judge_checks(self, request: CheckRequest) -> CheckResponse:
        """Stage 2: judge only the supplied check/subject pairs.

        Raises:
            AiUnavailableError: the provider could not be reached.
            AiResponseInvalidError: the response failed the strict schema.
        """
        ...
