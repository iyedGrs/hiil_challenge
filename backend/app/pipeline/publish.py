"""Check instantiation, judgment validation and atomic publication (B5, B6, B7).

Three responsibilities, in the order the pipeline uses them:

1. **Instantiate** the reviewed checklist against the case's stable subjects. The
   model only ever receives checks the backend already found eligible, and never
   receives a legal reference (B5). Checks with ``basis="reconciliation"`` are
   withheld entirely because ``Decimal`` code decides them (B7). Subjects that
   disappeared are published ``not_applicable`` without asking anybody (B5, B7).

2. **Validate** what came back. Unknown or duplicated check/subject pairs are
   rejected; ``satisfied``/``contradicted`` require at least one cited *verified*
   fact; a citation to a quarantined or unknown fact invalidates the judgment
   rather than being silently dropped (B6). Where coverage was incomplete, an
   unqualified "not found" is downgraded to ``PARTIAL_COVERAGE`` or
   ``SOURCE_UNREADABLE`` so absence is never overstated (B6, BE-09).

3. **Publish** atomically, after validation. Invalid output never becomes an empty
   success (B7). Findings are keyed ``(case_id, check_id, subject_id)`` so identity
   survives re-runs, and the delta is computed against the previous published run
   rather than from array position.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ai.base import CheckInstanceInput
from app.ai.contracts import CheckResponse, ModelCheckResult
from app.domain.enums import (
    AnalysisStatus,
    CheckResult,
    Delta,
    ExecutionMode,
    FindingStatus,
    LegalCoverage,
    ReasonCode,
    ResponseAction,
)
from app.ids import ANALYSIS_PREFIX, FINDING_PREFIX, new_id
from app.models.analysis import Analysis, CheckResultRow
from app.models.base import utcnow
from app.models.fact import Fact
from app.models.finding import Finding, FindingResponse
from app.models.legal import Check
from app.models.subject import Subject
from app.pipeline.reconcile import RECONCILIATION_CHECK_ID, ReconciliationOutcome

logger = logging.getLogger("app.pipeline.publish")

#: ``basis`` value marking a check decided by deterministic code (B7).
BACKEND_DECIDED_BASIS = "reconciliation"

#: Backend-rendered messages. The model's own wording is never published as the
#: finding text (B6); these are the strings a preparer reads.
_MESSAGES: dict[tuple[str, ReasonCode], str] = {
    ("invoice_issued", ReasonCode.EVIDENCE_FOUND): "La facture a été lue dans les pièces déposées.",
    ("invoice_issued", ReasonCode.EVIDENCE_NOT_FOUND): (
        "Aucune facture lisible n'a été trouvée dans les pièces examinées."
    ),
    ("contract_or_order_evidence", ReasonCode.EVIDENCE_FOUND): (
        "Une référence de contrat ou de commande a été trouvée dans les pièces examinées."
    ),
    ("contract_or_order_evidence", ReasonCode.EVIDENCE_NOT_FOUND): (
        "Aucune preuve du contrat ou de la commande n'a été trouvée dans les pièces examinées."
    ),
    ("delivery_evidence", ReasonCode.EVIDENCE_FOUND): (
        "Une preuve de réception des marchandises a été trouvée dans les pièces examinées."
    ),
    ("delivery_evidence", ReasonCode.EVIDENCE_NOT_FOUND): (
        "Aucune preuve de réception n'a été trouvée dans les pièces examinées."
    ),
    ("payment_or_credit_note_evidence", ReasonCode.EVIDENCE_FOUND): (
        "Des paiements ou notes de crédit ont été trouvés dans les pièces examinées."
    ),
    ("payment_or_credit_note_evidence", ReasonCode.EVIDENCE_NOT_FOUND): (
        "Aucun paiement ni note de crédit n'a été trouvé dans les pièces examinées."
    ),
    ("referenced_attachment_present", ReasonCode.EVIDENCE_FOUND): (
        "L'annexe citée figure parmi les fichiers déposés."
    ),
    ("referenced_attachment_present", ReasonCode.EVIDENCE_NOT_FOUND): (
        "Une annexe est citée dans les pièces mais n'a pas été trouvée parmi les fichiers déposés."
    ),
}

#: Fallbacks by reason code, used when a check has no specific wording. Neutral by
#: design: they describe the reviewed material, never intent or fraud (F4).
_GENERIC_MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.EVIDENCE_FOUND: "Un élément justificatif a été trouvé dans les pièces examinées.",
    ReasonCode.EVIDENCE_NOT_FOUND: "Cet élément n'a pas été trouvé dans les pièces examinées.",
    ReasonCode.CONFLICT: "Les pièces examinées présentent une incohérence à clarifier.",
    ReasonCode.SOURCE_UNREADABLE: (
        "Une ou plusieurs pages n'ont pas pu être lues, donc cet élément n'a pas pu être vérifié."
    ),
    ReasonCode.PARTIAL_COVERAGE: (
        "La vérification est incomplète : une partie des pièces n'a pas pu être examinée."
    ),
    ReasonCode.AMBIGUOUS_LINK: (
        "Le rattachement de cet élément à la facture n'est pas établi de façon certaine."
    ),
    ReasonCode.INVALID_SOURCE: (
        "Une citation n'a pas pu être retrouvée dans le texte enregistré, donc elle n'est pas retenue."
    ),
    ReasonCode.NOT_APPLICABLE: "Cet élément ne s'applique plus à ce dossier.",
    ReasonCode.LEGAL_COVERAGE_UNAVAILABLE: (
        "Aucun référentiel juridique validé n'est disponible pour cette vérification."
    ),
}


@dataclass
class Instantiation:
    """The check instances for one run, split by who decides them."""

    #: Handed to the model.
    model_checks: list[CheckInstanceInput] = field(default_factory=list)
    #: Decided by Decimal code; never sent to the model (B7).
    backend_checks: list[CheckInstanceInput] = field(default_factory=list)
    #: Published ``not_applicable`` because their subject no longer exists (B7).
    not_applicable: list[CheckInstanceInput] = field(default_factory=list)
    #: Checklist metadata by ``check_id`` for publication.
    definitions: dict[str, Check] = field(default_factory=dict)


@dataclass
class ValidatedJudgment:
    """One judgment that passed validation and may be published."""

    check_id: str
    subject_id: str
    result: CheckResult
    reason_code: ReasonCode
    fact_ids: list[str]
    explanation: str | None


@dataclass
class Coverage:
    """The processing manifest, computed from work actually done (B6)."""

    reviewed_pages: int
    unreadable_pages: int
    rejected_facts: int

    @property
    def is_partial(self) -> bool:
        return self.unreadable_pages > 0 or self.rejected_facts > 0

    def as_dict(self) -> dict[str, int]:
        return {
            "reviewed_pages": self.reviewed_pages,
            "unreadable_pages": self.unreadable_pages,
            "rejected_facts": self.rejected_facts,
        }


def _latest_explanation(
    db: DbSession, case_id: str, check_id: str, subject_id: str
) -> str | None:
    """Return the preparer's most recent explanation for this finding, if any."""
    row = db.scalar(
        select(FindingResponse)
        .join(Finding, Finding.id == FindingResponse.finding_id)
        .where(
            Finding.case_id == case_id,
            Finding.check_id == check_id,
            Finding.subject_id == subject_id,
        )
        .order_by(FindingResponse.created_at.desc())
        .limit(1)
    )
    return row.explanation if row is not None else None


def instantiate_checks(
    db: DbSession,
    *,
    case_id: str,
    case_type: str,
    pack_version: str,
    subjects: list[Subject],
) -> Instantiation:
    """Instantiate the reviewed checklist against ``subjects`` (spec/backend.md B5).

    A check applies when its ``applies_when.case_type`` matches the case's
    confirmed type -- evaluated by backend code, never chosen by the model. Each
    applicable check is instantiated once per active subject of its declared
    ``subject_type``.

    Inactive subjects that already carry a finding are instantiated too, as
    ``not_applicable`` candidates: their history is retained and they are never
    reported as resolved by evidence (B7, BE-10).
    """
    definitions = {
        check.check_id: check
        for check in db.scalars(
            select(Check).where(Check.pack_version == pack_version).order_by(Check.sort_order)
        ).all()
    }
    existing_keys = {
        (finding.check_id, finding.subject_id)
        for finding in db.scalars(select(Finding).where(Finding.case_id == case_id)).all()
    }

    result = Instantiation(definitions=definitions)
    by_id = {subject.subject_id: subject for subject in subjects}

    for check in definitions.values():
        applies_to = check.applies_when.get("case_type")
        if applies_to is not None and applies_to != case_type:
            continue

        for subject in subjects:
            if subject.subject_type != check.subject_type:
                continue
            instance = CheckInstanceInput(
                check_id=check.check_id,
                subject_id=subject.subject_id,
                subject_type=subject.subject_type.value,
                subject_label=subject.label or subject.subject_id,
                label=check.label,
                satisfied_by=tuple(check.satisfied_by),
                preparer_explanation=_latest_explanation(
                    db, case_id, check.check_id, subject.subject_id
                ),
            )
            if subject.is_active:
                target = (
                    result.backend_checks
                    if check.basis == BACKEND_DECIDED_BASIS
                    else result.model_checks
                )
                target.append(instance)
            elif (check.check_id, subject.subject_id) in existing_keys:
                result.not_applicable.append(instance)

    # Subjects removed from the working case are not in ``subjects`` at all when
    # they were hard-removed; those still present but inactive are handled above.
    del by_id
    logger.info(
        "Instantiated checks: model=%d backend=%d not_applicable=%d",
        len(result.model_checks),
        len(result.backend_checks),
        len(result.not_applicable),
    )
    return result


def _coverage_downgrade(reason: ReasonCode, coverage: Coverage) -> ReasonCode:
    """Qualify an absence claim when coverage was incomplete (B6, BE-09).

    "Not found" is only publishable as such when everything relevant was actually
    read. With unreadable pages the honest answer is ``SOURCE_UNREADABLE``; with
    discarded extraction output it is ``PARTIAL_COVERAGE``.
    """
    if reason is not ReasonCode.EVIDENCE_NOT_FOUND:
        return reason
    if coverage.unreadable_pages > 0:
        return ReasonCode.SOURCE_UNREADABLE
    if coverage.rejected_facts > 0:
        return ReasonCode.PARTIAL_COVERAGE
    return reason


def validate_judgments(
    *,
    instantiation: Instantiation,
    response: CheckResponse,
    verified_fact_ids: set[str],
    coverage: Coverage,
) -> tuple[dict[tuple[str, str], ValidatedJudgment], list[str]]:
    """Validate Stage 2 output against what was actually asked (B6).

    Returns:
        ``(judgments_by_pair, problems)``. A pair missing from the result is left
        for the caller to publish as unassessable; ``problems`` lists sanitized
        descriptions of what was rejected, for logging only.
    """
    expected = {(check.check_id, check.subject_id) for check in instantiation.model_checks}
    judgments: dict[tuple[str, str], ValidatedJudgment] = {}
    problems: list[str] = []

    for judgment in response.checks:
        key = (judgment.check_id, judgment.subject_id)
        if key not in expected:
            problems.append(f"unknown check/subject pair rejected: {judgment.check_id}")
            continue
        if key in judgments:
            problems.append(f"duplicate judgment rejected: {judgment.check_id}")
            continue

        cited = [fact_id for fact_id in judgment.fact_ids if fact_id in verified_fact_ids]
        if len(cited) != len(judgment.fact_ids):
            # A citation we cannot verify makes the whole judgment unsupported;
            # dropping just the bad ID would publish a weaker claim as if intact.
            problems.append(f"unverifiable fact citation rejected: {judgment.check_id}")
            judgments[key] = ValidatedJudgment(
                check_id=judgment.check_id,
                subject_id=judgment.subject_id,
                result=CheckResult.unassessable,
                reason_code=ReasonCode.INVALID_SOURCE,
                fact_ids=[],
                explanation=None,
            )
            continue

        result = CheckResult(judgment.result.value)
        if judgment.result in {ModelCheckResult.satisfied, ModelCheckResult.contradicted} and not cited:
            # No support means no supported conclusion (B6).
            problems.append(f"uncited {judgment.result.value} downgraded: {judgment.check_id}")
            judgments[key] = ValidatedJudgment(
                check_id=judgment.check_id,
                subject_id=judgment.subject_id,
                result=CheckResult.unassessable,
                reason_code=_coverage_downgrade(ReasonCode.EVIDENCE_NOT_FOUND, coverage),
                fact_ids=[],
                explanation=None,
            )
            continue

        reason = ReasonCode(judgment.reason_code.value)
        if result is CheckResult.unassessable:
            reason = _coverage_downgrade(reason, coverage)

        judgments[key] = ValidatedJudgment(
            check_id=judgment.check_id,
            subject_id=judgment.subject_id,
            result=result,
            reason_code=reason,
            fact_ids=cited,
            explanation=judgment.explanation or None,
        )

    for key in expected - set(judgments):
        problems.append(f"missing judgment defaulted to unassessable: {key[0]}")
        judgments[key] = ValidatedJudgment(
            check_id=key[0],
            subject_id=key[1],
            result=CheckResult.unassessable,
            reason_code=_coverage_downgrade(ReasonCode.EVIDENCE_NOT_FOUND, coverage),
            fact_ids=[],
            explanation=None,
        )

    return judgments, problems


def _message_for(check_id: str, reason: ReasonCode, override: str | None = None) -> str:
    """Return the backend-rendered message for a published check."""
    if override:
        return override
    specific = _MESSAGES.get((check_id, reason))
    if specific:
        return specific
    return _GENERIC_MESSAGES.get(reason, "Cet élément nécessite une vérification.")


def _is_issue(result: CheckResult) -> bool:
    """Whether a result represents an open issue for the preparer to act on."""
    return result in {CheckResult.contradicted, CheckResult.unassessable}


def publish_run(
    db: DbSession,
    *,
    case_id: str,
    revision: int,
    execution_mode: ExecutionMode,
    checklist_version: str,
    legal_coverage: LegalCoverage,
    model_version: str,
    prompt_version: str,
    normalization_version: str,
    input_snapshot: dict[str, object],
    coverage: Coverage,
    instantiation: Instantiation,
    judgments: dict[tuple[str, str], ValidatedJudgment],
    reconciliation: ReconciliationOutcome | None,
    facts_by_id: dict[str, Fact],
    reviewed_document_ids: list[str],
    job_id: str | None,
    disclosures: list[str],
) -> Analysis:
    """Write the analysis, its check results and finding identity atomically (B7).

    The caller owns the transaction, so either the whole run appears or none of it
    does. Status is ``partial`` whenever coverage was incomplete, which keeps a
    run with unreadable pages or discarded facts from being presented as a clean
    dossier (B7, BE-09).
    """
    previous = db.scalar(
        select(Analysis)
        .where(Analysis.case_id == case_id)
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    previous_rows: dict[tuple[str, str], CheckResultRow] = {}
    if previous is not None:
        previous_rows = {
            (row.check_id, row.subject_id): row
            for row in db.scalars(
                select(CheckResultRow).where(CheckResultRow.analysis_id == previous.id)
            ).all()
        }

    analysis = Analysis(
        id=new_id(ANALYSIS_PREFIX),
        case_id=case_id,
        revision=revision,
        status=AnalysisStatus.partial if coverage.is_partial else AnalysisStatus.ready,
        execution_mode=execution_mode,
        checklist_version=checklist_version,
        legal_coverage=legal_coverage,
        model_version=model_version,
        prompt_version=prompt_version,
        normalization_version=normalization_version,
        input_snapshot=input_snapshot,
        coverage=coverage.as_dict(),
        reconciliation=reconciliation.payload if reconciliation else None,
        disclosures=disclosures,
        reviewed_document_ids=reviewed_document_ids,
        job_id=job_id,
        published_at=utcnow(),
    )
    db.add(analysis)
    db.flush()

    def _write(
        instance: CheckInstanceInput,
        result: CheckResult,
        reason: ReasonCode,
        fact_ids: list[str],
        explanation: str | None,
        message_override: str | None = None,
    ) -> None:
        definition = instantiation.definitions.get(instance.check_id)
        finding = db.scalar(
            select(Finding).where(
                Finding.case_id == case_id,
                Finding.check_id == instance.check_id,
                Finding.subject_id == instance.subject_id,
            )
        )
        previous_row = previous_rows.get((instance.check_id, instance.subject_id))

        if result is CheckResult.not_applicable:
            finding_status: FindingStatus | None = None
            delta: Delta | None = Delta.not_applicable
        elif _is_issue(result):
            finding_status = FindingStatus.open
            if previous_row is None:
                delta = Delta.new
            elif previous_row.finding_status is FindingStatus.open:
                delta = Delta.still_open
            elif previous_row.finding_status is FindingStatus.resolved:
                delta = Delta.reopened
            else:
                delta = Delta.new
        else:
            # Satisfied. Only call it "resolved" if there was an open issue to
            # resolve; otherwise no issue ever existed and both fields stay null.
            had_open_issue = (
                previous_row is not None and previous_row.finding_status is FindingStatus.open
            ) or (finding is not None and finding.status is FindingStatus.open)
            finding_status = FindingStatus.resolved if had_open_issue else None
            delta = Delta.resolved if had_open_issue else None

        if finding is None:
            finding = Finding(
                id=new_id(FINDING_PREFIX),
                case_id=case_id,
                check_id=instance.check_id,
                subject_id=instance.subject_id,
                status=finding_status or FindingStatus.resolved,
                first_seen_analysis_id=analysis.id if finding_status is FindingStatus.open else None,
            )
            db.add(finding)
            db.flush()
        elif finding_status is FindingStatus.open and finding.first_seen_analysis_id is None:
            finding.first_seen_analysis_id = analysis.id

        if finding_status is not None:
            finding.status = finding_status
        finding.last_result = result
        finding.last_reason_code = reason
        finding.last_delta = delta
        finding.last_seen_analysis_id = analysis.id
        finding.resolved_at = utcnow() if finding_status is FindingStatus.resolved else None

        evidence_refs = []
        for fact_id in fact_ids:
            fact = facts_by_id.get(fact_id)
            if fact is None:
                continue
            evidence_refs.append(
                {
                    "fact_id": fact.id,
                    "document_id": fact.document_id,
                    "page": fact.page,
                    "source_text": fact.source_text,
                }
            )

        db.add(
            CheckResultRow(
                analysis_id=analysis.id,
                check_id=instance.check_id,
                subject_id=instance.subject_id,
                case_id=case_id,
                finding_id=finding.id,
                result=result,
                reason_code=reason,
                finding_status=finding_status,
                delta=delta,
                basis=definition.basis if definition else "checklist",
                message=_message_for(instance.check_id, reason, message_override),
                explanation=explanation,
                evidence_refs=evidence_refs,
                fact_ids=list(fact_ids),
                reviewed_document_ids=reviewed_document_ids,
                # Copied from the reviewed checklist, never from model output (B5).
                legal_reference_ids=list(definition.legal_reference_ids) if definition else [],
                actions=[
                    action
                    for action in (definition.actions if definition else [])
                    if action in {member.value for member in ResponseAction}
                ],
            )
        )

    for instance in instantiation.model_checks:
        judgment = judgments[(instance.check_id, instance.subject_id)]
        _write(
            instance,
            judgment.result,
            judgment.reason_code,
            judgment.fact_ids,
            judgment.explanation,
        )

    for instance in instantiation.backend_checks:
        if instance.check_id == RECONCILIATION_CHECK_ID and reconciliation is not None:
            _write(
                instance,
                reconciliation.result,
                reconciliation.reason_code,
                reconciliation.fact_ids,
                None,
                message_override=reconciliation.message,
            )
        else:
            _write(
                instance,
                CheckResult.unassessable,
                ReasonCode.EVIDENCE_NOT_FOUND,
                [],
                None,
            )

    for instance in instantiation.not_applicable:
        _write(instance, CheckResult.not_applicable, ReasonCode.NOT_APPLICABLE, [], None)

    db.flush()
    logger.info(
        "Published analysis=%s case=%s revision=%d status=%s",
        analysis.id,
        case_id,
        revision,
        analysis.status.value,
    )
    return analysis
