"""Backend-owned stable subjects (spec/backend.md B6, B7).

Finding identity is ``(case_id, check_id, subject_id)``, so subjects must survive
revisions and same-subject replacements. Every subject is created here by
application code; the model can neither mint one nor merge two (B6).

Two canonical subjects always exist for a case, created from the claim itself
rather than from any document:

* ``transaction_0001`` -- the commercial transaction being disputed;
* ``invoice_0001`` -- the invoice the claim is about.

They exist even with zero uploaded files, which is what lets the first assessment
report "no delivery evidence found" as a real finding instead of having nothing to
attach it to.

Derived subjects (payments, credit notes, referenced annexes) are created from
*verified* facts only, matched on a natural key so a re-run reuses the same
subject rather than allocating a new sequence number.

Linkage is never inferred from a matching amount alone (B7). A subject whose
identity or link is uncertain is kept with ``linkage_confirmed=False``, and
reconciliation refuses to resolve while any relevant link is unconfirmed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ai.contracts import FactKind
from app.domain.enums import SubjectType
from app.ids import next_subject_id
from app.models.base import utcnow
from app.models.case import ClaimRevision
from app.models.fact import Fact
from app.models.subject import Subject
from app.money import format_amount

logger = logging.getLogger("app.pipeline.subjects")

#: Fact kinds attributed to the canonical invoice subject.
_INVOICE_FACT_KINDS: frozenset[str] = frozenset(
    {
        FactKind.invoice_number.value,
        FactKind.invoice_total.value,
        FactKind.invoice_subtotal.value,
        FactKind.invoice_date.value,
        FactKind.delivery_confirmation.value,
        FactKind.delivery_date.value,
    }
)

#: Fact kinds attributed to the canonical transaction subject.
_TRANSACTION_FACT_KINDS: frozenset[str] = frozenset(
    {
        FactKind.contract_reference.value,
        FactKind.order_reference.value,
        FactKind.party_name.value,
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize_reference(value: str) -> str:
    """Return a comparison form for an identifier used as a natural key."""
    return _NON_ALNUM.sub("", value.casefold())


@dataclass
class SubjectSet:
    """The subjects available to one analysis run."""

    transaction: Subject
    invoice: Subject
    payments: list[Subject]
    credit_notes: list[Subject]
    annexes: list[Subject]

    @property
    def all_active(self) -> list[Subject]:
        subjects = [self.transaction, self.invoice, *self.payments, *self.credit_notes, *self.annexes]
        return [subject for subject in subjects if subject.is_active]


def _find_or_create(
    db: DbSession,
    *,
    case_id: str,
    subject_type: SubjectType,
    natural_key: dict[str, object],
    label: str,
    revision: int,
    source_document_id: str | None = None,
    linked_subject_id: str | None = None,
    linkage_confirmed: bool = False,
) -> Subject:
    """Return the subject matching ``natural_key``, creating it if absent (B7).

    Matching happens in Python over the case's subjects of this type rather than
    with a JSON query: the set is bounded by the case file limits, and keeping the
    comparison here makes the identity rule explicit and portable.

    ``natural_key`` is matched as a **subset** of the stored identifiers, not by
    equality. Identifiers get enriched as later runs learn more about a subject
    (an invoice number discovered on the second upload, say), and an equality test
    would then stop recognising the subject and allocate a new sequence -- which
    would silently break finding identity across revisions (B7, BE-10).
    """
    existing = list(
        db.scalars(
            select(Subject).where(
                Subject.case_id == case_id, Subject.subject_type == subject_type
            )
        ).all()
    )
    for subject in existing:
        stored = subject.identifiers or {}
        if all(stored.get(key) == value for key, value in natural_key.items()):
            # Reactivate: the subject reappearing in a later revision is the same
            # subject, not a new one (B7).
            subject.is_active = True
            subject.removed_at = None
            subject.label = label
            if source_document_id is not None:
                subject.source_document_id = source_document_id
            subject.linked_subject_id = linked_subject_id
            subject.linkage_confirmed = linkage_confirmed
            return subject

    subject_id = next_subject_id(db, case_id, subject_type)
    sequence = int(subject_id.rsplit("_", 1)[1])
    subject = Subject(
        case_id=case_id,
        subject_id=subject_id,
        subject_type=subject_type,
        sequence=sequence,
        label=label,
        identifiers=natural_key,
        linked_subject_id=linked_subject_id,
        linkage_confirmed=linkage_confirmed,
        source_document_id=source_document_id,
        is_active=True,
        first_seen_revision=revision,
    )
    db.add(subject)
    db.flush()
    logger.info("Subject created: case=%s subject=%s", case_id, subject_id)
    return subject


def ensure_canonical_subjects(
    db: DbSession, *, case_id: str, claim: ClaimRevision, revision: int
) -> tuple[Subject, Subject]:
    """Create or refresh ``transaction_0001`` and ``invoice_0001`` (B6, B7).

    Labels come from the claim, so a preparer reads "Facture réclamée -- Demo
    Customer" rather than an opaque ID. The canonical natural keys are fixed
    strings, which is what keeps these two subjects singular per case.
    """
    transaction = _find_or_create(
        db,
        case_id=case_id,
        subject_type=SubjectType.transaction,
        natural_key={"canonical": "claim_transaction"},
        label=f"Transaction : {claim.claimant_name} / {claim.counterparty_name}",
        revision=revision,
        linkage_confirmed=True,
    )
    invoice = _find_or_create(
        db,
        case_id=case_id,
        subject_type=SubjectType.invoice,
        natural_key={"canonical": "claim_invoice"},
        label=f"Facture réclamée ({claim.counterparty_name})",
        revision=revision,
        linked_subject_id=transaction.subject_id,
        linkage_confirmed=True,
    )
    return transaction, invoice


def build_subjects(
    db: DbSession,
    *,
    case_id: str,
    claim: ClaimRevision,
    revision: int,
    verified_facts: list[Fact],
) -> SubjectSet:
    """Create/refresh every subject for this run and attribute facts to them.

    Payment and credit-note subjects are keyed by their **normalized amount**,
    which is how the same payment appearing in both a receipt and a bank statement
    resolves to one subject instead of being counted twice (B7, BE-08).

    The known limitation of that key is recorded deliberately: two genuinely
    distinct payments of an identical amount collapse into one subject. That
    direction is the safe one -- it understates payments received rather than
    inventing a second one -- and reconciliation labels its result as based on the
    uploaded records. Resolving it properly needs explicit payment references or a
    preparer confirmation, which B7 names as the prerequisite for treating two
    records as the same payment.

    A monetary fact whose amount could not be resolved unambiguously produces a
    subject with ``linkage_confirmed=False``, which blocks reconciliation rather
    than contributing a guessed number.
    """
    transaction, invoice = ensure_canonical_subjects(
        db, case_id=case_id, claim=claim, revision=revision
    )

    payments: dict[str, Subject] = {}
    credit_notes: dict[str, Subject] = {}
    annexes: dict[str, Subject] = {}

    for fact in verified_facts:
        if fact.kind in _INVOICE_FACT_KINDS:
            fact.subject_id = invoice.subject_id
            if fact.kind == FactKind.invoice_number.value and not invoice.identifiers.get(
                "invoice_number"
            ):
                # Record the discovered invoice number without changing the
                # canonical natural key, so identity stays stable.
                invoice.identifiers = {
                    **invoice.identifiers,
                    "invoice_number": fact.value_text,
                }
                invoice.label = f"Facture {fact.value_text}"
            continue

        if fact.kind in _TRANSACTION_FACT_KINDS:
            fact.subject_id = transaction.subject_id
            continue

        if fact.kind == FactKind.payment_amount.value:
            resolved = fact.normalized_value is not None
            key = format_amount(fact.normalized_value) if resolved else f"unresolved:{fact.id}"
            if key not in payments:
                payments[key] = _find_or_create(
                    db,
                    case_id=case_id,
                    subject_type=SubjectType.payment,
                    natural_key={"amount": key},
                    label=(
                        f"Paiement de {key} {fact.currency_text or claim.currency.value}"
                        if resolved
                        else f"Paiement d'un montant illisible ({fact.value_text})"
                    ),
                    revision=revision,
                    source_document_id=fact.document_id,
                    linked_subject_id=invoice.subject_id,
                    # An unresolved amount is not a confirmed link (B7).
                    linkage_confirmed=resolved,
                )
            fact.subject_id = payments[key].subject_id
            continue

        if fact.kind == FactKind.credit_note_amount.value:
            resolved = fact.normalized_value is not None
            key = format_amount(fact.normalized_value) if resolved else f"unresolved:{fact.id}"
            if key not in credit_notes:
                credit_notes[key] = _find_or_create(
                    db,
                    case_id=case_id,
                    subject_type=SubjectType.credit_note,
                    natural_key={"amount": key},
                    label=(
                        f"Note de crédit de {key} {fact.currency_text or claim.currency.value}"
                        if resolved
                        else f"Note de crédit d'un montant illisible ({fact.value_text})"
                    ),
                    revision=revision,
                    source_document_id=fact.document_id,
                    linked_subject_id=invoice.subject_id,
                    linkage_confirmed=resolved,
                )
            fact.subject_id = credit_notes[key].subject_id
            continue

        if fact.kind == FactKind.annex_reference.value:
            key = _normalize_reference(fact.value_text)
            if not key:
                continue
            if key not in annexes:
                annexes[key] = _find_or_create(
                    db,
                    case_id=case_id,
                    subject_type=SubjectType.referenced_annex,
                    natural_key={"reference": key},
                    label=f"Annexe {fact.value_text}",
                    revision=revision,
                    source_document_id=fact.document_id,
                    linked_subject_id=transaction.subject_id,
                    linkage_confirmed=True,
                )
            fact.subject_id = annexes[key].subject_id
            continue

        # Any other kind stays attributed to the transaction it belongs to.
        fact.subject_id = transaction.subject_id

    db.flush()
    return SubjectSet(
        transaction=transaction,
        invoice=invoice,
        payments=list(payments.values()),
        credit_notes=list(credit_notes.values()),
        annexes=list(annexes.values()),
    )


def deactivate_missing_subjects(
    db: DbSession, *, case_id: str, active_subject_ids: set[str]
) -> list[Subject]:
    """Mark subjects that no longer exist in the working case as inactive (B7).

    History is retained and their checks become ``not_applicable`` on the next
    run; a subject that disappeared is never reported as "resolved by evidence".
    """
    removed: list[Subject] = []
    for subject in db.scalars(select(Subject).where(Subject.case_id == case_id)).all():
        if subject.subject_id in active_subject_ids:
            continue
        if subject.is_active:
            subject.is_active = False
            subject.removed_at = utcnow()
            removed.append(subject)
    if removed:
        db.flush()
    return removed
