"""Automatic case readiness verdict (spec/progress.md change log).

``compute_readiness`` is pure: no database, no I/O. The wiring tests at the
bottom exercise the case detail and submission gate through the real API.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import AnalysisStatus, CheckResult, ExecutionMode, ReadinessStatus
from app.pipeline.readiness import CheckOutcome, compute_readiness
from tests.test_handoff import force_complete_verdict, prepared_case

SATISFIED = CheckOutcome(
    check_id="invoice_issued", subject_label="Facture", result=CheckResult.satisfied, message="ok"
)
NOT_APPLICABLE = CheckOutcome(
    check_id="x", subject_label="X", result=CheckResult.not_applicable, message="n/a"
)
CONTRADICTED = CheckOutcome(
    check_id="claim_amount_matches_records",
    subject_label="Montant réclamé",
    result=CheckResult.contradicted,
    message="Montant réclamé 20000.000 TND ≠ solde documenté 15000.000 TND.",
)


def _base(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        case_revision=3,
        analysis_revision=3,
        analysis_status=AnalysisStatus.ready,
        execution_mode=ExecutionMode.live,
        unreadable_pages=0,
        checks=[SATISFIED, NOT_APPLICABLE],
    )
    base.update(overrides)
    return base


def test_complete_when_everything_lines_up() -> None:
    result = compute_readiness(**_base())
    assert result.status is ReadinessStatus.complete
    assert result.reasons == []


def test_needs_analysis_when_no_analysis_exists() -> None:
    result = compute_readiness(**_base(analysis_revision=None))
    assert result.status is ReadinessStatus.needs_analysis
    assert result.reasons


def test_needs_analysis_when_analysis_is_for_an_older_revision() -> None:
    result = compute_readiness(**_base(analysis_revision=2, case_revision=3))
    assert result.status is ReadinessStatus.needs_analysis


def test_incomplete_when_execution_mode_is_fixture() -> None:
    result = compute_readiness(**_base(execution_mode=ExecutionMode.fixture))
    assert result.status is ReadinessStatus.incomplete
    assert any("simul" in reason for reason in result.reasons)


def test_incomplete_when_analysis_status_is_partial() -> None:
    result = compute_readiness(**_base(analysis_status=AnalysisStatus.partial))
    assert result.status is ReadinessStatus.incomplete
    assert any("incomplète" in reason for reason in result.reasons)


def test_incomplete_when_pages_are_unreadable() -> None:
    result = compute_readiness(**_base(unreadable_pages=2))
    assert result.status is ReadinessStatus.incomplete
    assert any("page(s)" in reason for reason in result.reasons)


def test_incomplete_when_a_check_is_not_satisfied() -> None:
    result = compute_readiness(**_base(checks=[SATISFIED, CONTRADICTED]))
    assert result.status is ReadinessStatus.incomplete
    assert any("solde documenté" in reason for reason in result.reasons)


def test_incomplete_reports_one_reason_per_failing_condition() -> None:
    result = compute_readiness(
        **_base(
            execution_mode=ExecutionMode.fixture,
            analysis_status=AnalysisStatus.partial,
            unreadable_pages=1,
            checks=[CONTRADICTED],
        )
    )
    assert result.status is ReadinessStatus.incomplete
    assert len(result.reasons) == 4


# --- Wiring: case detail and the submission gate --------------------------


def test_case_detail_reports_incomplete_verdict_for_a_fixture_analysis(
    client: TestClient, db: Session, seeded: None
) -> None:
    """A fixture-mode run can never be "complete" (AI_MODE=fixture in tests)."""
    case_id, _revision, _analysis_id, headers = prepared_case(client, db)

    body = client.get(f"/api/cases/{case_id}", headers=headers).json()

    assert body["readiness"]["status"] == ReadinessStatus.incomplete.value
    assert any("simul" in reason for reason in body["readiness"]["reasons"])


def test_submission_is_refused_for_an_incomplete_case(
    client: TestClient, db: Session, seeded: None
) -> None:
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]

    refused = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "CASE_NOT_COMPLETE"


def test_submission_succeeds_once_the_verdict_is_complete(
    client: TestClient, db: Session, seeded: None
) -> None:
    """Flip the published run to a real, fully-satisfied one, then submit."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)

    accepted = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    )

    assert accepted.status_code == 201, accepted.text
    detail = client.get(f"/api/cases/{case_id}", headers=headers).json()
    assert detail["readiness"]["status"] == ReadinessStatus.complete.value
