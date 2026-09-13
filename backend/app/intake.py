"""Cheap intake gate (spec/backend.md B3).

Runs *before* any expensive document assessment and makes **zero** provider
calls. Deterministic schema validation already happened in
``app/schemas/cases.py``; this module implements step 2 of the gate flow:
application checks that detect a blank or generic description, an insufficient
transaction description and unresolved required questions, and return targeted,
stable questions.

Step 3 of B3 (one bounded semantic model call) is deliberately not implemented.
B12 states that if the schedule slips, the optional semantic intake AI is the
first thing to drop -- ahead of provenance or deterministic arithmetic. The
``gate_unavailable`` status stays in the contract for a future live gate; the
rules here never produce it, because rules cannot be unavailable.

Question IDs are stable strings so the UI can anchor a question to an input and
so an unchanged claim revision reuses its cached result (B3). ``field`` uses the
claim-relative path the UI understands (``narrative``, ``claimed_amount``,
``dates.invoice``).

Readiness is not a decision on the merits: ``ready`` only means there is enough
information to attempt the supported document checks (B3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domain.enums import IntakeStatus
from app.money import parse_claim_amount

#: Version tag for the rule set, stored on the claim revision alongside the
#: cached result so a rule change can be told apart from a stale cache.
GATE_VERSION: Final[str] = "rules-v1"

#: Cap on returned questions (spec/backend.md B3: "at most five").
MAX_QUESTIONS: Final[int] = 5

#: A narrative shorter than this cannot describe a commercial transaction.
MIN_MEANINGFUL_NARRATIVE_CHARS: Final[int] = 40

#: Distinct-word floor. Catches "aaa aaa aaa ..." padding that clears the
#: character floor without carrying information.
MIN_DISTINCT_WORDS: Final[int] = 8

#: Narratives that are placeholders rather than descriptions. Matched against the
#: whole trimmed, lower-cased narrative, not as substrings, so a real sentence
#: containing the word "test" is not rejected.
_PLACEHOLDER_NARRATIVES: Final[frozenset[str]] = frozenset(
    {
        "test",
        "n/a",
        "na",
        "none",
        "aucun",
        "aucun commentaire",
        "voir pieces",
        "voir pièces",
        "voir documents",
        "see documents",
        "see attached",
        "rien a signaler",
        "rien à signaler",
        "asdf",
        "lorem ipsum",
    }
)

#: Words indicating *what* was supplied. French, English and Arabic, because the
#: UI is French and sources may be Arabic (D10). A generous list on purpose: the
#: gate must not block a legitimate description over vocabulary.
_GOODS_KEYWORDS: Final[tuple[str, ...]] = (
    "marchandise",
    "marchandises",
    "bien",
    "biens",
    "produit",
    "produits",
    "article",
    "articles",
    "matériel",
    "materiel",
    "mobilier",
    "meuble",
    "meubles",
    "équipement",
    "equipement",
    "fourniture",
    "fournitures",
    "livraison",
    "livré",
    "livre",
    "livrée",
    "commande",
    "stock",
    "lot",
    "pièce",
    "piece",
    "pièces détachées",
    "goods",
    "furniture",
    "equipment",
    "supplies",
    "delivered",
    "delivery",
    "order",
    "shipment",
    "products",
    "items",
    "بضاعة",
    "سلع",
    "منتجات",
    "تسليم",
    "أثاث",
)

#: Words indicating the payment situation being disputed.
_PAYMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "paiement",
    "payé",
    "paye",
    "payée",
    "impayé",
    "impaye",
    "impayée",
    "non payé",
    "non paye",
    "facture",
    "factures",
    "règlement",
    "reglement",
    "solde",
    "dette",
    "créance",
    "creance",
    "versement",
    "virement",
    "acompte",
    "échéance",
    "echeance",
    "relance",
    "payment",
    "paid",
    "unpaid",
    "invoice",
    "outstanding",
    "balance",
    "owed",
    "owes",
    "settle",
    "overdue",
    "دفع",
    "فاتورة",
    "غير مدفوع",
    "رصيد",
    "مستحق",
)

_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Question:
    """One targeted intake question (spec/backend.md B3, B9)."""

    id: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        """Return the JSON shape stored on the claim revision."""
        return {"id": self.id, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class GateResult:
    """Outcome of the cheap gate for one claim revision."""

    status: IntakeStatus
    questions: tuple[Question, ...]

    @property
    def is_ready(self) -> bool:
        return self.status is IntakeStatus.ready


# Question catalogue. Messages are French (D10) and neutral: they ask for
# information, they never accuse or judge the claim.
QUESTION_DESCRIBE_TRANSACTION = Question(
    id="describe_transaction",
    field="narrative",
    message=(
        "Décrivez la transaction plus précisément : ce qui a été fourni, à qui, "
        "quand, et ce qui est contesté."
    ),
)
QUESTION_DESCRIBE_GOODS = Question(
    id="describe_goods",
    field="narrative",
    message="Quels biens ou marchandises ont été fournis ?",
)
QUESTION_DESCRIBE_PAYMENT = Question(
    id="describe_payment_status",
    field="narrative",
    message="Quel paiement reste contesté, et qu'avez-vous déjà reçu le cas échéant ?",
)
QUESTION_INVOICE_DATE = Question(
    id="invoice_date",
    field="dates.invoice",
    message=(
        "Indiquez la date de la facture si vous la connaissez ; laissez vide si elle "
        "est inconnue."
    ),
)
QUESTION_CLAIMED_AMOUNT = Question(
    id="claimed_amount_zero",
    field="claimed_amount",
    message="Le montant réclamé est de zéro. Confirmez le montant réellement réclamé.",
)


def _contains_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in haystack for keyword in keywords)


def _answered(answers: dict[str, str], question: Question, *, min_length: int = 10) -> bool:
    """Return True when ``question`` has a substantive stored answer.

    A follow-up answer resolves its question so the preparer is not asked the
    same thing forever when the missing detail was supplied in the answer field
    rather than by rewriting the narrative (B3).
    """
    answer = answers.get(question.id, "").strip()
    return len(answer) >= min_length


def evaluate_gate(
    *,
    narrative: str,
    claimed_amount: str,
    invoice_date_known: bool,
    follow_up_answers: list[dict[str, str]],
) -> GateResult:
    """Evaluate the cheap gate for one claim revision (spec/backend.md B3).

    Args:
        narrative: The stored, already length-validated narrative. Treated purely
            as data; no instruction inside it is honoured (B15).
        claimed_amount: Canonical decimal string from the claim.
        invoice_date_known: Whether ``dates.invoice`` is set.
        follow_up_answers: Stored ``{question_id, answer}`` entries.

    Returns:
        ``ready`` when the supported document checks can be attempted, otherwise
        ``needs_information`` with at most :data:`MAX_QUESTIONS` targeted
        questions.
    """
    answers = {
        entry["question_id"]: entry.get("answer", "")
        for entry in follow_up_answers
        if "question_id" in entry
    }
    text = narrative.strip()
    lowered = text.lower()
    words = _WORD_PATTERN.findall(lowered)
    distinct_words = len(set(words))

    questions: list[Question] = []

    insufficient = (
        lowered in _PLACEHOLDER_NARRATIVES
        or len(text) < MIN_MEANINGFUL_NARRATIVE_CHARS
        or distinct_words < MIN_DISTINCT_WORDS
    )
    if insufficient and not _answered(answers, QUESTION_DESCRIBE_TRANSACTION, min_length=40):
        questions.append(QUESTION_DESCRIBE_TRANSACTION)

    # Combine narrative and answers when looking for the required detail: an
    # answer supplies it just as well as a rewritten narrative.
    combined = " ".join([lowered, *(value.lower() for value in answers.values())])

    if not _contains_keyword(combined, _GOODS_KEYWORDS):
        questions.append(QUESTION_DESCRIBE_GOODS)
    if not _contains_keyword(combined, _PAYMENT_KEYWORDS):
        questions.append(QUESTION_DESCRIBE_PAYMENT)

    try:
        amount = parse_claim_amount(claimed_amount)
    except ValueError:
        # Schema validation already rejected malformed amounts; treat an
        # unparseable value here as zero rather than crashing the gate.
        amount = Decimal("0")
    if amount == 0 and not _answered(answers, QUESTION_CLAIMED_AMOUNT, min_length=1):
        questions.append(QUESTION_CLAIMED_AMOUNT)

    if not questions:
        # Ready: no question is returned, so the UI shows a clean intake rather
        # than a hint next to an input it cannot act on.
        return GateResult(status=IntakeStatus.ready, questions=())

    if not invoice_date_known and not _answered(answers, QUESTION_INVOICE_DATE, min_length=1):
        # Only asked alongside a genuinely blocking gap. An unknown invoice date
        # stays explicitly unknown rather than being fabricated (B3), so it never
        # blocks readiness on its own.
        questions.append(QUESTION_INVOICE_DATE)

    return GateResult(
        status=IntakeStatus.needs_information, questions=tuple(questions[:MAX_QUESTIONS])
    )
