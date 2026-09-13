"""Deterministic monetary reconciliation (spec/backend.md B7).

The **only** place in this system that produces a monetary conclusion. Every value
is a :class:`~decimal.Decimal` parsed from a validated source fact or from the
preparer's typed claim; no float is involved and no currency is ever converted.
The model contributes nothing here beyond having copied the source strings, and it
has no schema field in which to return a balance (see :mod:`app.ai.contracts`).

Scope is deliberately narrow, exactly as B7 asks: one invoice total against
explicitly linked payment and credit-note records.

``documented_balance = invoice_total - linked_payments - linked_credit_notes``

is computed **only** when every input and every link is unambiguous. Otherwise the
run publishes an unresolved reconciliation check rather than a number.

Two honesty rules that are easy to get wrong and are enforced here:

* An absent receipt is not proof that nothing was paid. The result is always
  labelled as based on the uploaded records (``coverage_note``).
* A negative balance is preserved as a possible overpayment or credit. It is never
  clamped to zero.

Not computed at all in this MVP: penalties, interest, tax corrections, damages and
payment-plan terms. Excess precision is never silently rounded away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from app.ai.contracts import FactKind
from app.domain.enums import CheckResult, ReasonCode
from app.models.fact import Fact
from app.models.subject import Subject
from app.money import format_amount

logger = logging.getLogger("app.pipeline.reconcile")

#: The check the reconciliation outcome is published under. Declared in the legal
#: pack with ``basis="reconciliation"``, which marks it backend-decided and keeps
#: it out of the set handed to the model (B5, B7).
RECONCILIATION_CHECK_ID = "claim_amount_matches_records"


@dataclass
class ReconciliationOutcome:
    """Result of attempting reconciliation for one case revision."""

    result: CheckResult
    reason_code: ReasonCode
    message: str
    #: ``{documented_balance, currency, source_fact_ids, coverage_note}`` or None
    #: when nothing could be resolved.
    payload: dict[str, object] | None = None
    fact_ids: list[str] = field(default_factory=list)


def _unambiguous_amounts(facts: list[Fact]) -> tuple[list[Fact], bool]:
    """Split facts into resolvable ones and report whether any was ambiguous.

    A fact with ``normalized_value is None`` had a token this system refuses to
    interpret (for example ``1,000``). Its presence blocks reconciliation.
    """
    resolved = [fact for fact in facts if fact.normalized_value is not None]
    has_ambiguous = len(resolved) != len(facts)
    return resolved, has_ambiguous


def _deduplicated_by_subject(facts: list[Fact]) -> dict[str, Fact]:
    """Keep one fact per subject, so a payment counted twice is counted once.

    Payment and credit-note subjects are keyed by normalized amount in
    :mod:`app.pipeline.subjects`, so a receipt and a bank statement describing the
    same 5 000 TND transfer share a subject and collapse here (B7, BE-08).
    """
    by_subject: dict[str, Fact] = {}
    for fact in facts:
        if fact.subject_id is None:
            continue
        by_subject.setdefault(fact.subject_id, fact)
    return by_subject


def reconcile(
    *,
    claimed_amount: Decimal,
    currency: str,
    verified_facts: list[Fact],
    subjects_by_id: dict[str, Subject],
) -> ReconciliationOutcome:
    """Reconcile the claim against the uploaded records (spec/backend.md B7).

    Args:
        claimed_amount: The preparer's typed claim. It comes from structured input,
            never from model output.
        currency: The claim currency. Mixed or ambiguous currency is not
            reconciled.
        verified_facts: Facts that passed source validation.
        subjects_by_id: Subjects for the case, used to check that every
            contributing link is confirmed.

    Returns:
        A :class:`ReconciliationOutcome`. ``payload`` is present only when a
        balance was actually computed.
    """
    totals = [f for f in verified_facts if f.kind == FactKind.invoice_total.value]
    payments = [f for f in verified_facts if f.kind == FactKind.payment_amount.value]
    credit_notes = [f for f in verified_facts if f.kind == FactKind.credit_note_amount.value]

    if not totals:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.EVIDENCE_NOT_FOUND,
            message=(
                "Aucun montant total de facture n'a pu être lu dans les pièces examinées, "
                "donc le montant réclamé n'a pas pu être comparé aux documents."
            ),
        )

    resolved_totals, totals_ambiguous = _unambiguous_amounts(totals)
    if totals_ambiguous or not resolved_totals:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.AMBIGUOUS_LINK,
            message=(
                "Le format d'un montant de facture est ambigu, donc aucun solde n'a été "
                "calculé. Vérifiez le montant ou fournissez une copie plus lisible."
            ),
            fact_ids=[fact.id for fact in totals],
        )

    # Mixed currency is not reconciled: no conversion ever happens (B7).
    currencies = {
        (fact.currency_text or currency).upper()
        for fact in resolved_totals + payments + credit_notes
    }
    if len(currencies) > 1:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.AMBIGUOUS_LINK,
            message=(
                "Les pièces mentionnent plusieurs devises. Aucune conversion n'est "
                "effectuée, donc aucun solde n'a été calculé."
            ),
            fact_ids=[fact.id for fact in resolved_totals],
        )

    distinct_totals = {fact.normalized_value for fact in resolved_totals}
    if len(distinct_totals) > 1:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.CONFLICT,
            message=(
                "Plusieurs montants totaux différents ont été lus dans les pièces. "
                "Indiquez lequel correspond à la facture réclamée."
            ),
            fact_ids=[fact.id for fact in resolved_totals],
        )

    resolved_payments, payments_ambiguous = _unambiguous_amounts(payments)
    resolved_credits, credits_ambiguous = _unambiguous_amounts(credit_notes)
    if payments_ambiguous or credits_ambiguous:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.AMBIGUOUS_LINK,
            message=(
                "Le format d'un montant de paiement ou de note de crédit est ambigu, "
                "donc aucun solde n'a été calculé."
            ),
            fact_ids=[fact.id for fact in payments + credit_notes],
        )

    payment_facts = _deduplicated_by_subject(resolved_payments)
    credit_facts = _deduplicated_by_subject(resolved_credits)

    unconfirmed = [
        subject_id
        for subject_id in list(payment_facts) + list(credit_facts)
        if not (subjects_by_id.get(subject_id) and subjects_by_id[subject_id].linkage_confirmed)
    ]
    if unconfirmed:
        return ReconciliationOutcome(
            result=CheckResult.unassessable,
            reason_code=ReasonCode.AMBIGUOUS_LINK,
            message=(
                "Le rattachement d'un paiement à cette facture n'est pas établi, donc "
                "aucun solde n'a été calculé. Confirmez à quelle facture il correspond."
            ),
            fact_ids=[fact.id for fact in payment_facts.values()],
        )

    invoice_total: Decimal = resolved_totals[0].normalized_value  # type: ignore[assignment]
    paid = sum(
        (fact.normalized_value for fact in payment_facts.values()), start=Decimal("0")
    )
    credited = sum(
        (fact.normalized_value for fact in credit_facts.values()), start=Decimal("0")
    )
    documented_balance = invoice_total - paid - credited

    source_fact_ids = [
        resolved_totals[0].id,
        *[fact.id for fact in payment_facts.values()],
        *[fact.id for fact in credit_facts.values()],
    ]
    coverage_note = (
        "Solde établi d'après les documents déposés uniquement. "
        f"Total de facture retenu : {format_amount(invoice_total)} {currency}. "
        f"Paiements rattachés : {format_amount(paid)} {currency}. "
        f"Notes de crédit rattachées : {format_amount(credited)} {currency}. "
        "L'absence d'un reçu ne prouve pas qu'aucun paiement n'a été effectué."
    )
    payload: dict[str, object] = {
        "documented_balance": format_amount(documented_balance),
        "currency": currency,
        "source_fact_ids": source_fact_ids,
        "coverage_note": coverage_note,
    }

    logger.info(
        "Reconciled: total=%s paid=%s credited=%s balance=%s claimed=%s",
        invoice_total,
        paid,
        credited,
        documented_balance,
        claimed_amount,
    )

    if documented_balance == claimed_amount:
        return ReconciliationOutcome(
            result=CheckResult.satisfied,
            reason_code=ReasonCode.EVIDENCE_FOUND,
            message=(
                f"Le montant réclamé ({format_amount(claimed_amount)} {currency}) correspond "
                f"au solde établi d'après les documents déposés."
            ),
            payload=payload,
            fact_ids=source_fact_ids,
        )

    # Negative balances are preserved and named for what they are (B7).
    if documented_balance < 0:
        detail = (
            f"Les documents déposés indiquent un trop-perçu possible de "
            f"{format_amount(-documented_balance)} {currency}."
        )
    else:
        detail = (
            f"Les documents déposés indiquent un solde de "
            f"{format_amount(documented_balance)} {currency}."
        )
    return ReconciliationOutcome(
        result=CheckResult.contradicted,
        reason_code=ReasonCode.CONFLICT,
        message=(
            f"Le montant réclamé est de {format_amount(claimed_amount)} {currency}. {detail} "
            "Corrigez la réclamation ou ajoutez la pièce manquante."
        ),
        payload=payload,
        fact_ids=source_fact_ids,
    )
