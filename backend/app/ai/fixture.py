"""Deterministic fixture adapter (spec/local-dev.md L3, spec/backend.md B6).

``AI_MODE=fixture`` runs the whole pipeline with **no provider call at all**. This
adapter stands in for the model by reading the *real* stored page text with
deterministic rules, so the facts it returns carry genuine provenance: a quote it
reports is a line that actually exists on that page, and it still has to pass the
same source validation as live output (B7).

That matters for two reasons:

1. It exercises the real validators, persistence, identity and publication path
   rather than bypassing them, which is exactly what L5 asks of fixture mode.
2. It is honest. Output produced here is published with
   ``execution_mode=fixture`` and must be labelled as such in the UI; it is never
   presented as a live AI result (F2, L3).

The rules are intentionally shallow keyword/pattern matching. They are not a
model and not an accuracy claim: they are a reproducible stand-in whose behaviour
a reviewer can read in one file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.ai.base import CheckRequest, DocumentInput, ValidatedFactInput
from app.ai.contracts import (
    CandidateFact,
    CheckJudgment,
    CheckResponse,
    DocumentTypeLabel,
    ExtractionResponse,
    FactKind,
    ModelCheckResult,
    ModelReasonCode,
)

#: Recorded as the model version on everything this adapter produces, so a
#: fixture-derived fact is never mistaken for a live one in stored provenance.
FIXTURE_MODEL_VERSION: Final[str] = "fixture-rules-v1"

#: Page states whose text may be read. An unreadable page contributes nothing and
#: is reported as a reading issue instead of being silently treated as empty.
_READABLE_STATES: Final[frozenset[str]] = frozenset({"ready", "partial"})

# --- Amount and identifier patterns -----------------------------------------

#: One monetary token. Grouping by space/apostrophe/dot/comma is accepted here;
#: deciding what the separators *mean* is :mod:`app.money`'s job, and it refuses
#: ambiguous tokens rather than guessing.
_AMOUNT = re.compile(
    r"(?<![\w.,])"
    r"(\d{1,3}(?:[ \u00a0\u202f'.,]\d{3})+(?:[.,]\d{1,3})?|\d+(?:[.,]\d{1,3})?)"
    r"(?![\w])"
)

_IDENTIFIER = r"([A-Za-z0-9][A-Za-z0-9\-/_]{1,31})"

_INVOICE_NUMBER = re.compile(
    r"(?:facture|invoice|فاتورة)\s*(?:n[°ºo]?\.?|no\.?|num[eé]ro|number|#)?\s*[:\-]?\s*" + _IDENTIFIER,
    re.IGNORECASE,
)
_CONTRACT_REFERENCE = re.compile(
    r"(?:contrat|contract|convention)\s*(?:n[°ºo]?\.?|no\.?|num[eé]ro|number|#)?\s*[:\-]?\s*"
    + _IDENTIFIER,
    re.IGNORECASE,
)
_ORDER_REFERENCE = re.compile(
    r"(?:bon de commande|purchase order|commande|order)\s*"
    r"(?:n[°ºo]?\.?|no\.?|num[eé]ro|number|#)?\s*[:\-]?\s*" + _IDENTIFIER,
    re.IGNORECASE,
)
_PAYMENT_REFERENCE = re.compile(
    r"(?:r[eé]f[eé]rence|reference|r[eé]f\.?|virement|transfer|transaction|avis)\s*"
    r"(?:n[°ºo]?\.?|no\.?|#)?\s*[:\-]?\s*" + _IDENTIFIER,
    re.IGNORECASE,
)
_ANNEX_REFERENCE = re.compile(
    r"(?:annexe|annex|appendice|appendix|ملحق)\s*(?:n[°ºo]?\.?|no\.?)?\s*[:\-]?\s*([A-Za-z0-9]{1,8})",
    re.IGNORECASE,
)
#: ISO, French and dotted date forms.
_DATE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|"
    r"\d{1,2}\s+(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|"
    r"octobre|novembre|d[eé]cembre|january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4})",
    re.IGNORECASE,
)

# --- Keyword vocabularies ----------------------------------------------------

_DOCUMENT_TYPE_KEYWORDS: Final[dict[DocumentTypeLabel, tuple[str, ...]]] = {
    DocumentTypeLabel.delivery_note: (
        "bon de livraison",
        "bordereau de livraison",
        "delivery note",
        "packing list",
        "accuse de reception",
        "accusé de réception",
        "recu de livraison",
        "reçu de livraison",
        "goods received",
        "marchandise recue",
        "marchandise reçue",
        "سند تسليم",
    ),
    DocumentTypeLabel.payment_receipt: (
        "recu de paiement",
        "reçu de paiement",
        "payment receipt",
        "ordre de virement",
        "avis de virement",
        "avis de credit",
        "avis de crédit",
        "quittance",
        "transfer receipt",
        "وصل دفع",
    ),
    DocumentTypeLabel.bank_statement: (
        "releve bancaire",
        "relevé bancaire",
        "bank statement",
        "extrait de compte",
        "releve de compte",
        "relevé de compte",
    ),
    DocumentTypeLabel.credit_note: (
        "note de credit",
        "note de crédit",
        "credit note",
        "facture d'avoir",
        "avoir n",
    ),
    DocumentTypeLabel.purchase_order: (
        "bon de commande",
        "purchase order",
    ),
    DocumentTypeLabel.contract: (
        "contrat",
        "contract",
        "convention",
        "conditions generales",
        "conditions générales",
        "عقد",
    ),
    DocumentTypeLabel.invoice: (
        "facture",
        "invoice",
        "total ttc",
        "total h.t",
        "total ht",
        "tva",
        "فاتورة",
    ),
    DocumentTypeLabel.correspondence: (
        "objet :",
        "cordialement",
        "dear ",
        "madame,",
        "monsieur,",
        "best regards",
    ),
}

#: Lines that state a payable total.
_TOTAL_KEYWORDS: Final[tuple[str, ...]] = (
    "total ttc",
    "total a payer",
    "total à payer",
    "montant total",
    "total du",
    "total dû",
    "total due",
    "net a payer",
    "net à payer",
    "grand total",
    "total general",
    "total général",
    "المجموع",
)

#: Lines that state a pre-tax or intermediate total. Kept separate so
#: reconciliation can never add a subtotal to a total (B7).
_SUBTOTAL_KEYWORDS: Final[tuple[str, ...]] = (
    "sous-total",
    "sous total",
    "subtotal",
    "sub-total",
    "total ht",
    "total h.t",
    "montant ht",
)

_DELIVERY_KEYWORDS: Final[tuple[str, ...]] = (
    "bon de livraison",
    "livraison effectuee",
    "livraison effectuée",
    "marchandise livree",
    "marchandise livrée",
    "marchandises livrees",
    "marchandises livrées",
    "recu en bon etat",
    "reçu en bon état",
    "accuse de reception",
    "accusé de réception",
    "bien recu",
    "bien reçu",
    "goods received",
    "received in good condition",
    "delivered on",
    "delivery confirmed",
    "signature du client",
    "تم التسليم",
)

_PAYMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "paiement",
    "payment",
    "virement",
    "versement",
    "acompte",
    "regle",
    "réglé",
    "reglement",
    "règlement",
    "paid",
    "transfer of",
    "credite",
    "crédité",
    "quittance",
    "دفع",
)

_CREDIT_NOTE_KEYWORDS: Final[tuple[str, ...]] = (
    "note de credit",
    "note de crédit",
    "credit note",
    "avoir",
    "remise accordee",
    "remise accordée",
)

_INVOICE_DATE_KEYWORDS: Final[tuple[str, ...]] = (
    "date de facture",
    "date facture",
    "invoice date",
    "facture du",
    "date d'emission",
    "date d'émission",
)

_DELIVERY_DATE_KEYWORDS: Final[tuple[str, ...]] = (
    "date de livraison",
    "delivery date",
    "livre le",
    "livré le",
    "delivered on",
)

_PAYMENT_DATE_KEYWORDS: Final[tuple[str, ...]] = (
    "date de paiement",
    "payment date",
    "date de valeur",
    "paye le",
    "payé le",
)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> str | None:
    """Return the first needle found in ``haystack``, else ``None``."""
    for needle in needles:
        if needle in haystack:
            return needle
    return None


@dataclass(frozen=True)
class _Line:
    """One source line with its page number."""

    page: int
    text: str
    lowered: str


def _readable_lines(document: DocumentInput) -> list[_Line]:
    """Return the non-empty lines of every readable page (B4).

    Lines are kept verbatim (only outer whitespace trimmed) because they become
    ``source_text`` and must still match the stored page text (B7).
    """
    lines: list[_Line] = []
    for page in document.pages:
        if page.state not in _READABLE_STATES:
            continue
        for raw in page.text.splitlines():
            text = raw.strip()
            if text:
                lines.append(_Line(page=page.page, text=text, lowered=text.casefold()))
    return lines


def _classify(lines: list[_Line]) -> DocumentTypeLabel | None:
    """Pick the document type with the most keyword hits (spec/backend.md B6).

    Scoring rather than first-match, because an invoice mentions "livraison" and a
    delivery note mentions "facture". ``None`` when nothing matched at all: an
    unknown type is reported as unknown, not guessed.
    """
    body = "\n".join(line.lowered for line in lines)
    scores: dict[DocumentTypeLabel, int] = {}
    for label, keywords in _DOCUMENT_TYPE_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in body)
        if hits:
            scores[label] = hits
    if not scores:
        return None
    best = max(scores.values())
    # Deterministic tie-break: the declaration order of the keyword table, which
    # puts the more specific document types first.
    for label in _DOCUMENT_TYPE_KEYWORDS:
        if scores.get(label) == best:
            return label
    return None  # pragma: no cover - unreachable, best came from scores


def _fact(
    kind: FactKind,
    value_text: str,
    document_id: str,
    line: _Line,
    currency_text: str | None = None,
) -> CandidateFact:
    """Build one candidate fact quoting ``line`` verbatim."""
    return CandidateFact(
        kind=kind,
        value_text=value_text,
        currency_text=currency_text,
        document_id=document_id,
        page=line.page,
        source_text=line.text,
    )


#: Currency labels recognised on a line. Detecting a label never converts
#: anything; the currency travels with the amount (B7).
_CURRENCY_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("tnd", "TND"),
    ("dinars", "TND"),
    ("dinar", "TND"),
    ("د.ت", "TND"),
    ("dt", "TND"),
)

#: Words that make a bare number on the line a monetary amount.
_AMOUNT_KEYWORDS: Final[tuple[str, ...]] = (
    "total",
    "montant",
    "somme",
    "net a payer",
    "net à payer",
    "amount",
    "prix",
    "valeur",
    "المجموع",
)

#: How far from a number a currency label may sit and still bind to it.
_CURRENCY_WINDOW: Final[int] = 6


def _currency_in(text: str) -> str | None:
    """Return the currency label present on the line, if any. Never converted."""
    lowered = text.casefold()
    for token, label in _CURRENCY_LABELS:
        if token in lowered:
            return label
    return None


def _adjacent_currency(text: str, start: int, end: int) -> str | None:
    """Return the currency label immediately around ``text[start:end]``, if any."""
    before = text[max(0, start - _CURRENCY_WINDOW) : start].casefold()
    after = text[end : end + _CURRENCY_WINDOW].casefold()
    for token, label in _CURRENCY_LABELS:
        if token in after or token in before:
            return label
    return None


def _monetary_tokens(line: _Line) -> list[tuple[str, str | None]]:
    """Return the numeric tokens on ``line`` that are genuinely monetary.

    Without this, a reference number (``VIR-889021``) or a date (``2026-07-15``)
    on a line that happens to mention "paiement" would be read as an amount, and a
    fabricated payment would then flow into reconciliation. Two accepted shapes,
    both requiring positive evidence that the number is money:

    1. a currency label sits immediately beside the number (``20 000,000 TND``);
    2. the line states an amount (``Total``, ``Montant``, ``Somme`` ...) **and**
       carries exactly one numeric token, so there is no ambiguity about which
       number is meant.

    Everything else is left alone. Missing a real amount is recoverable -- the
    dependent check simply stays unassessable -- whereas inventing one would
    corrupt a monetary conclusion (B7).
    """
    matches = list(_AMOUNT.finditer(line.text))
    if not matches:
        return []

    with_currency: list[tuple[str, str | None]] = []
    for match in matches:
        currency = _adjacent_currency(line.text, match.start(1), match.end(1))
        if currency is not None:
            with_currency.append((match.group(1), currency))
    if with_currency:
        return with_currency

    if _contains_any(line.lowered, _AMOUNT_KEYWORDS) and len(matches) == 1:
        return [(matches[0].group(1), _currency_in(line.text))]
    return []


def _amount_facts_from_line(
    kind: FactKind, document_id: str, line: _Line
) -> list[CandidateFact]:
    """Extract every monetary token on ``line`` as ``kind``.

    The whole line is the quote, and the numeric token is the value, so the value
    is always anchored inside its own quote as B6 requires.
    """
    return [
        _fact(kind, token, document_id, line, currency_text=currency)
        for token, currency in _monetary_tokens(line)
    ]


class FixtureAiAdapter:
    """Rule-based stand-in for the configured model (spec/local-dev.md L3)."""

    model_version = FIXTURE_MODEL_VERSION
    execution_mode = "fixture"

    # --- Stage 1 ------------------------------------------------------------

    def extract_facts(self, document: DocumentInput) -> ExtractionResponse:
        """Return candidate facts for one document (spec/backend.md B6).

        Reads only stored page text. Amounts are copied source strings; nothing
        here is summed, converted or derived.
        """
        lines = _readable_lines(document)
        reading_issues = [
            f"page {page.page} is {page.state}"
            for page in document.pages
            if page.state not in _READABLE_STATES
        ]
        document_type = _classify(lines)
        facts: list[CandidateFact] = []

        for line in lines:
            facts.extend(self._facts_for_line(document.document_id, line, document_type))

        return ExtractionResponse(
            document_id=document.document_id,
            document_type=document_type,
            facts=self._dedupe(facts),
            reading_issues=reading_issues,
        )

    def _facts_for_line(
        self, document_id: str, line: _Line, document_type: DocumentTypeLabel | None
    ) -> list[CandidateFact]:
        """Apply every extraction rule to one line."""
        facts: list[CandidateFact] = []

        # Monetary lines. Subtotal is checked first so a "Total HT" line is never
        # also admitted as a payable total (B7).
        if _contains_any(line.lowered, _SUBTOTAL_KEYWORDS):
            facts.extend(_amount_facts_from_line(FactKind.invoice_subtotal, document_id, line))
        elif _contains_any(line.lowered, _TOTAL_KEYWORDS) or line.lowered.startswith("total"):
            if document_type is DocumentTypeLabel.credit_note:
                facts.extend(
                    _amount_facts_from_line(FactKind.credit_note_amount, document_id, line)
                )
            else:
                facts.extend(_amount_facts_from_line(FactKind.invoice_total, document_id, line))

        if _contains_any(line.lowered, _CREDIT_NOTE_KEYWORDS):
            facts.extend(_amount_facts_from_line(FactKind.credit_note_amount, document_id, line))

        if _contains_any(line.lowered, _PAYMENT_KEYWORDS):
            facts.extend(_amount_facts_from_line(FactKind.payment_amount, document_id, line))

        # A bank statement or payment receipt states payments even on lines that
        # carry no payment verb.
        if document_type in {
            DocumentTypeLabel.payment_receipt,
            DocumentTypeLabel.bank_statement,
        } and not _contains_any(line.lowered, _PAYMENT_KEYWORDS):
            if _contains_any(line.lowered, ("montant", "amount", "somme", "credit", "crédit")):
                facts.extend(
                    _amount_facts_from_line(FactKind.payment_amount, document_id, line)
                )

        # Delivery / receipt evidence.
        delivery_phrase = _contains_any(line.lowered, _DELIVERY_KEYWORDS)
        if delivery_phrase:
            start = line.lowered.index(delivery_phrase)
            facts.append(
                _fact(
                    FactKind.delivery_confirmation,
                    line.text[start : start + len(delivery_phrase)],
                    document_id,
                    line,
                )
            )

        # Identifiers and dates.
        for pattern, kind in (
            (_INVOICE_NUMBER, FactKind.invoice_number),
            (_CONTRACT_REFERENCE, FactKind.contract_reference),
            (_ORDER_REFERENCE, FactKind.order_reference),
            (_ANNEX_REFERENCE, FactKind.annex_reference),
        ):
            match = pattern.search(line.text)
            if match:
                facts.append(_fact(kind, match.group(1), document_id, line))

        if _contains_any(line.lowered, _PAYMENT_KEYWORDS) or document_type in {
            DocumentTypeLabel.payment_receipt,
            DocumentTypeLabel.bank_statement,
        }:
            match = _PAYMENT_REFERENCE.search(line.text)
            if match:
                facts.append(_fact(FactKind.payment_reference, match.group(1), document_id, line))

        for keywords, kind in (
            (_INVOICE_DATE_KEYWORDS, FactKind.invoice_date),
            (_DELIVERY_DATE_KEYWORDS, FactKind.delivery_date),
            (_PAYMENT_DATE_KEYWORDS, FactKind.payment_date),
        ):
            if _contains_any(line.lowered, keywords):
                match = _DATE.search(line.text)
                if match:
                    facts.append(_fact(kind, match.group(1), document_id, line))

        return facts

    @staticmethod
    def _dedupe(facts: list[CandidateFact]) -> list[CandidateFact]:
        """Drop exact repeats of the same kind/value/page/quote."""
        seen: set[tuple[str, str, int, str]] = set()
        unique: list[CandidateFact] = []
        for fact in facts:
            key = (fact.kind.value, fact.value_text, fact.page, fact.source_text)
            if key in seen:
                continue
            seen.add(key)
            unique.append(fact)
        return unique

    # --- Stage 2 ------------------------------------------------------------

    def judge_checks(self, request: CheckRequest) -> CheckResponse:
        """Judge only the supplied check/subject pairs (spec/backend.md B6).

        Returns no ``monetary_facts``: Stage 1 already extracted every amount, and
        this adapter has no reason to re-quote them. It never returns a computed
        value -- the schema has nowhere to put one.
        """
        by_kind: dict[str, list[ValidatedFactInput]] = {}
        for fact in request.facts:
            by_kind.setdefault(fact.kind, []).append(fact)

        judgments = [self._judge(check, by_kind) for check in request.checks]
        return CheckResponse(checks=judgments, monetary_facts=[])

    def _judge(
        self, check, by_kind: dict[str, list[ValidatedFactInput]]
    ) -> CheckJudgment:
        """Decide one instantiated check from the validated facts available."""
        supporting: list[ValidatedFactInput] = []

        if check.check_id == "invoice_issued":
            supporting = by_kind.get(FactKind.invoice_total.value, []) + by_kind.get(
                FactKind.invoice_number.value, []
            )
            found_message = "The invoice total and/or number was read from the uploaded file."
        elif check.check_id == "contract_or_order_evidence":
            supporting = by_kind.get(FactKind.contract_reference.value, []) + by_kind.get(
                FactKind.order_reference.value, []
            )
            found_message = "A contract or order reference was found in the supplied material."
        elif check.check_id == "delivery_evidence":
            supporting = by_kind.get(FactKind.delivery_confirmation.value, []) + by_kind.get(
                FactKind.delivery_date.value, []
            )
            found_message = "A receipt or delivery confirmation was found in the supplied material."
        elif check.check_id == "payment_or_credit_note_evidence":
            supporting = by_kind.get(FactKind.payment_amount.value, []) + by_kind.get(
                FactKind.credit_note_amount.value, []
            )
            found_message = "A payment or credit-note amount was found in the supplied material."
        elif check.check_id == "referenced_attachment_present":
            return self._judge_annex(check, by_kind)
        else:
            # An unknown check is abstained from rather than guessed at.
            return CheckJudgment(
                check_id=check.check_id,
                subject_id=check.subject_id,
                result=ModelCheckResult.unassessable,
                reason_code=ModelReasonCode.EVIDENCE_NOT_FOUND,
                fact_ids=[],
                explanation="This check has no fixture rule, so no judgment was made.",
            )

        if supporting:
            return CheckJudgment(
                check_id=check.check_id,
                subject_id=check.subject_id,
                result=ModelCheckResult.satisfied,
                reason_code=ModelReasonCode.EVIDENCE_FOUND,
                fact_ids=[fact.fact_id for fact in supporting[:10]],
                explanation=found_message,
            )
        return CheckJudgment(
            check_id=check.check_id,
            subject_id=check.subject_id,
            result=ModelCheckResult.unassessable,
            reason_code=ModelReasonCode.EVIDENCE_NOT_FOUND,
            fact_ids=[],
            explanation="No supporting evidence was found in the supplied readable material.",
        )

    @staticmethod
    def _judge_annex(check, by_kind: dict[str, list[ValidatedFactInput]]) -> CheckJudgment:
        """Judge a contract-referenced annex (spec/backend.md B6).

        The annex subject exists because a contract referenced it. It counts as
        present only when the same reference also appears in a *different*
        document, i.e. the annex itself was uploaded. One mention in the
        referencing contract alone proves only that it was referenced.
        """
        annex_facts = by_kind.get(FactKind.annex_reference.value, [])
        matching = [fact for fact in annex_facts if fact.subject_id == check.subject_id]
        documents = {fact.document_id for fact in matching}
        if len(documents) >= 2:
            return CheckJudgment(
                check_id=check.check_id,
                subject_id=check.subject_id,
                result=ModelCheckResult.satisfied,
                reason_code=ModelReasonCode.EVIDENCE_FOUND,
                fact_ids=[fact.fact_id for fact in matching[:10]],
                explanation="The referenced annex appears in an uploaded file as well.",
            )
        return CheckJudgment(
            check_id=check.check_id,
            subject_id=check.subject_id,
            result=ModelCheckResult.unassessable,
            reason_code=ModelReasonCode.EVIDENCE_NOT_FOUND,
            fact_ids=[fact.fact_id for fact in matching[:10]],
            explanation="The annex is referenced but was not found among the uploaded files.",
        )
