"""Automatic case readiness verdict (spec/progress.md change log).

The case gets a verdict decided by the AI analysis plus deterministic code, not
by a human reviewer. A reviewer only ever sees a read-only inbox. Legal
coverage stays ``unvalidated`` and does not block the verdict; this is still
not an official court filing.

``needs_analysis`` means no usable published analysis exists yet (none
published, or the latest one is for an older case revision). Otherwise the
verdict is ``complete`` only when the run was real (``execution_mode ==
live``), fully read (no unreadable pages), fully assessed (``ready``, not
``partial``) and every check -- including the deterministic reconciliation
check -- came back ``satisfied`` or ``not_applicable``. Any other case is
``incomplete``, with one French, user-facing reason per failing condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain.enums import AnalysisStatus, CheckResult, ExecutionMode, ReadinessStatus
from app.models.analysis import Analysis, CheckResultRow
from app.models.subject import Subject


@dataclass(frozen=True)
class CheckOutcome:
    """The minimal shape :func:`compute_readiness` needs for one check result."""

    check_id: str
    subject_label: str
    result: CheckResult
    message: str


@dataclass(frozen=True)
class Readiness:
    """The verdict and its French, user-facing reasons."""

    status: ReadinessStatus
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status.value, "reasons": self.reasons}


def compute_readiness(
    *,
    case_revision: int,
    analysis_revision: int | None,
    analysis_status: AnalysisStatus | None,
    execution_mode: ExecutionMode | None,
    unreadable_pages: int,
    checks: list[CheckOutcome],
) -> Readiness:
    """Pure verdict rule. No database access, no I/O."""
    if analysis_revision is None or analysis_revision != case_revision:
        return Readiness(
            ReadinessStatus.needs_analysis,
            ["Aucune analyse à jour n'a été publiée pour ce dossier."],
        )

    reasons: list[str] = []
    if execution_mode is not ExecutionMode.live:
        reasons.append("Analyse simulée : aucun verdict.")
    if analysis_status is AnalysisStatus.partial:
        reasons.append(
            "L'analyse est incomplète : une partie des pièces n'a pas pu être examinée."
        )
    if unreadable_pages > 0:
        reasons.append(
            f"{unreadable_pages} page(s) des pièces déposées n'ont pas pu être lues."
        )
    for outcome in checks:
        if outcome.result not in (CheckResult.satisfied, CheckResult.not_applicable):
            reasons.append(f"{outcome.subject_label} : {outcome.message}")

    if reasons:
        return Readiness(ReadinessStatus.incomplete, reasons)
    return Readiness(ReadinessStatus.complete, [])


def case_readiness(
    db: DbSession, *, case_revision: int, analysis: Analysis | None
) -> Readiness:
    """Gather the DB-backed inputs for ``analysis`` and apply the verdict rule."""
    if analysis is None:
        return compute_readiness(
            case_revision=case_revision,
            analysis_revision=None,
            analysis_status=None,
            execution_mode=None,
            unreadable_pages=0,
            checks=[],
        )

    rows = list(
        db.scalars(
            select(CheckResultRow).where(CheckResultRow.analysis_id == analysis.id)
        ).all()
    )
    labels = {
        subject_id: (label or subject_id)
        for subject_id, label in db.execute(
            select(Subject.subject_id, Subject.label).where(
                Subject.case_id == analysis.case_id
            )
        ).all()
    }
    coverage = analysis.coverage or {}
    checks = [
        CheckOutcome(
            check_id=row.check_id,
            subject_label=labels.get(row.subject_id, row.subject_id),
            result=row.result,
            message=row.message,
        )
        for row in rows
    ]
    return compute_readiness(
        case_revision=case_revision,
        analysis_revision=analysis.revision,
        analysis_status=analysis.status,
        execution_mode=analysis.execution_mode,
        unreadable_pages=int(coverage.get("unreadable_pages", 0)),
        checks=checks,
    )
