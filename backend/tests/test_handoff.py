"""Export, submission and reviewer back-office checks (spec/backend.md B10, B11).

Covers:

* **BE-12** - preparer/reviewer boundaries hold on every handoff route.
* **BE-14** - an explicitly acknowledged unresolved submission works, and the
  reviewer keeps seeing the exact version they received after the preparer edits
  the working case.
* B10 - the package is a real ZIP containing the summary, the checks, the
  originals and a manifest carrying the disclosures.

No network or AI provider call: ``AI_MODE`` is ``fixture``.
"""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER_NAME
from app.domain.enums import AnalysisStatus, CheckResult, ExecutionMode, ExportState, JobStatus, SubmissionState
from app.models.analysis import Analysis, CheckResultRow
from app.models.job import Job
from app.models.submission import Export
from app.pipeline.export import handle_export_job
from tests.conftest import DEMO_PASSWORD, DEMO_PREPARER_EMAIL, DEMO_REVIEWER_EMAIL
from tests.test_analysis import (
    DELIVERY_LINES,
    INVOICE_LINES,
    READY_CLAIM,
    RECEIPT_LINES,
    auth_headers,
    run_analysis,
    upload,
)

SECOND_PREPARER_EMAIL = "preparer2@demo.local"


def login_as(client: TestClient, email: str) -> dict[str, str]:
    token = client.post(
        "/api/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    ).json()["csrf_token"]
    return {CSRF_HEADER_NAME: token}


def prepared_case(client: TestClient, db: Session) -> tuple[str, int, str, dict[str, str]]:
    """Create a case with evidence and one published analysis.

    Returns ``(case_id, revision, analysis_id, preparer_headers)``.
    """
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)
    revision = upload(client, headers, case_id, revision, "livraison.pdf", DELIVERY_LINES)
    revision = upload(client, headers, case_id, revision, "recu.pdf", RECEIPT_LINES)
    analysis = run_analysis(client, db, headers, case_id, revision)
    return case_id, revision, analysis["analysis_id"], headers


def force_complete_verdict(db: Session, analysis_id: str) -> None:
    """Force ``analysis_id`` into a genuinely "complete" readiness verdict.

    The fixture pipeline deliberately leaves the demo claim/payment
    reconciliation mismatched (spec/backend.md BE-07), so tests that need a
    submittable dossier force the published run into the shape a clean live
    run would have published: real execution, full coverage, every check
    satisfied.
    """
    analysis = db.get(Analysis, analysis_id)
    assert analysis is not None
    analysis.execution_mode = ExecutionMode.live
    analysis.status = AnalysisStatus.ready
    for row in db.scalars(
        select(CheckResultRow).where(CheckResultRow.analysis_id == analysis_id)
    ).all():
        row.result = CheckResult.satisfied
        row.finding_status = None
    db.commit()


def run_export_job(client: TestClient, db: Session, job_id: str) -> None:
    """Execute the queued export job inline, mirroring the worker loop."""
    job = db.get(Job, job_id)
    assert job is not None
    job.status = JobStatus.running
    job.lease_owner = "inline-test"
    db.flush()
    handle_export_job(db, job)
    if job.status is JobStatus.running:
        job.status = JobStatus.succeeded
        job.lease_owner = None
    db.commit()


def test_recipients_are_server_owned(client: TestClient, seeded: None) -> None:
    """``GET /recipients`` lists seeded destinations, not arbitrary addresses (B9)."""
    auth_headers(client)

    body = client.get("/api/recipients").json()

    assert body["items"], "the demo reviewer destination should be listed"
    row = body["items"][0]
    assert row["recipient_id"].startswith("RCP_")
    assert row["name"]
    # The remit must not claim official filing or legal acceptance (B10).
    assert "no official filing" in row["remit"]


def test_incomplete_case_cannot_be_submitted(
    client: TestClient, db: Session, seeded: None
) -> None:
    """Submission is only reachable once the automatic verdict is "complete".

    Reviewers no longer decide completeness or acknowledge unresolved items
    (spec/progress.md change log: readiness verdict replaces reviewer
    approval); the ``acknowledge_unresolved`` field is still accepted for
    compatibility but no longer changes the outcome.
    """
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]

    refused = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
            "acknowledge_unresolved": True,
        },
    )
    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "CASE_NOT_COMPLETE"
    assert error["field_errors"]

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
    body = accepted.json()
    assert body["status"] == SubmissionState.submitted.value
    assert body["revision"] == revision
    assert body["analysis_id"] == analysis_id


def test_submission_stays_immutable_after_the_case_changes(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-14: the reviewer keeps seeing the version they received (B10)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)
    submission = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    ).json()

    detail_before = client.get("/api/cases/" + case_id).json()
    submitted_documents = len([d for d in detail_before["documents"] if d["active"]])

    # The preparer edits the working case: a new claim revision and a detached file.
    client.patch(
        f"/api/cases/{case_id}/claim",
        headers=headers,
        json={
            "expected_revision": revision,
            "claim": {**READY_CLAIM, "claimed_amount": "15000.000"},
        },
    )

    reviewer_headers = login_as(client, DEMO_REVIEWER_EMAIL)
    assert reviewer_headers
    snapshot = client.get(f"/api/reviewer/submissions/{submission['submission_id']}")
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()

    # Frozen: the original claimed amount and document set, not the edited ones.
    assert body["revision"] == revision
    assert body["claim"]["claimed_amount"] == "20000.000"
    assert len(body["documents"]) == submitted_documents
    assert body["analysis"]["analysis_id"] == analysis_id
    assert body["events"] == []


def test_reviewer_sees_only_assigned_submissions(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-12: the inbox is scoped, and preparers cannot use reviewer routes."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)
    submission_id = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    ).json()["submission_id"]

    # A preparer has no reviewer inbox.
    assert client.get("/api/reviewer/submissions").status_code == 404

    login_as(client, DEMO_REVIEWER_EMAIL)
    inbox = client.get("/api/reviewer/submissions").json()
    assert [row["submission_id"] for row in inbox["items"]] == [submission_id]
    assert inbox["items"][0]["claimant_name"] == "Demo Supplier"

    # A reviewer has no preparer routes and cannot read the working case.
    assert client.get(f"/api/cases/{case_id}").status_code == 404
    assert client.get("/api/cases").status_code == 404


def test_reviewer_can_read_submitted_originals_only(
    client: TestClient, db: Session, seeded: None
) -> None:
    """B10: submitted originals are reachable through authorized snapshot access."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)
    submission_id = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    ).json()["submission_id"]

    login_as(client, DEMO_REVIEWER_EMAIL)
    snapshot = client.get(f"/api/reviewer/submissions/{submission_id}").json()
    document_id = snapshot["documents"][0]["document_id"]

    content = client.get(f"/api/documents/{document_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "application/pdf"

    page = client.get(f"/api/documents/{document_id}/pages/1")
    assert page.status_code == 200
    assert page.json()["source_text"]

    # A second preparer, who received nothing, still cannot read it.
    login_as(client, SECOND_PREPARER_EMAIL)
    assert client.get(f"/api/documents/{document_id}/content").status_code == 404


def test_review_event_updates_state_and_reaches_preparer_activity(
    client: TestClient, db: Session, seeded: None
) -> None:
    """A clarification request is an event the preparer can see (B10, F4)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)
    submission_id = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    ).json()["submission_id"]

    reviewer_headers = login_as(client, DEMO_REVIEWER_EMAIL)
    received = client.post(
        f"/api/reviewer/submissions/{submission_id}/events",
        headers=reviewer_headers,
        json={"event_type": "received", "message": None},
    )
    assert received.status_code == 201
    assert received.json()["event_type"] == "received"

    clarification = client.post(
        f"/api/reviewer/submissions/{submission_id}/events",
        headers=reviewer_headers,
        json={
            "event_type": "clarification_requested",
            "message": "Merci de fournir le bon de commande signe.",
        },
    )
    assert clarification.status_code == 201

    snapshot = client.get(f"/api/reviewer/submissions/{submission_id}").json()
    assert [event["event_type"] for event in snapshot["events"]] == [
        "received",
        "clarification_requested",
    ]

    # Back on the preparer side, the request shows up in the case activity.
    auth_headers(client)
    activity = client.get(f"/api/cases/{case_id}").json()["activity"]
    types = [entry["type"] for entry in activity]
    assert "review_clarification_requested" in types
    assert "submission_sent" in types


def test_export_produces_a_real_package_with_disclosures(
    client: TestClient, db: Session, seeded: None
) -> None:
    """B10: one ZIP with summary, checks, originals and a manifest."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)

    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-1"},
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "acknowledge_unresolved": True,
        },
    )
    assert started.status_code == 202, started.text
    export_id = started.json()["export_id"]

    # Not ready before the worker runs.
    too_early = client.get(f"/api/exports/{export_id}/content")
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "EXPORT_NOT_READY"

    run_export_job(client, db, started.json()["job_id"])

    export = db.get(Export, export_id)
    assert export is not None
    assert export.state is ExportState.ready
    assert export.sha256 and export.byte_size

    content = client.get(f"/api/exports/{export_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "resume.pdf" in names
        assert "verifications.json" in names
        assert "index_des_pieces.json" in names
        assert any(name.startswith("originaux/") for name in names)

        manifest = json.loads(archive.read("manifest.json"))
        # Disclosures travel with the package, not only in the app (B10).
        assert manifest["legal_coverage"] == "unvalidated"
        assert "legal_coverage_unvalidated" in manifest["disclosures"]
        assert manifest["acknowledge_unresolved"] is True
        assert manifest["claim_is_an_allegation"] is True
        assert "No legal advice" in manifest["notice"]

        checks = json.loads(archive.read("verifications.json"))
        assert checks, "the package lists the validated checks"
        assert all(entry["legal_reference_ids"] == [] for entry in checks)

        assert archive.read("resume.pdf").startswith(b"%PDF")


def test_export_requires_a_current_published_analysis(
    client: TestClient, db: Session, seeded: None
) -> None:
    """B10: a stale run cannot be packaged as an assessed dossier."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)

    # Move the case on, leaving the analysis behind.
    new_revision = upload(client, headers, case_id, revision, "extra.pdf", DELIVERY_LINES)
    assert new_revision != revision

    response = client.post(
        f"/api/cases/{case_id}/exports",
        headers=headers,
        json={
            "expected_revision": new_revision,
            "analysis_id": analysis_id,
            "acknowledge_unresolved": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_OUTDATED"


def test_export_and_submission_are_owner_scoped(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-12: another preparer cannot export or submit somebody else's case."""
    case_id, revision, analysis_id, _headers = prepared_case(client, db)
    other = login_as(client, SECOND_PREPARER_EMAIL)

    export_response = client.post(
        f"/api/cases/{case_id}/exports",
        headers=other,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "acknowledge_unresolved": True,
        },
    )
    assert export_response.status_code == 404

    submission_response = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=other,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": "RCP_0000000000",
            "acknowledge_unresolved": True,
        },
    )
    assert submission_response.status_code == 404


def test_submission_appears_in_case_summaries(
    client: TestClient, db: Session, seeded: None
) -> None:
    """``GET /cases/{id}`` reports the submission the preparer sent (B9)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    recipient_id = client.get("/api/recipients").json()["items"][0]["recipient_id"]
    force_complete_verdict(db, analysis_id)
    submission_id = client.post(
        f"/api/cases/{case_id}/submissions",
        headers=headers,
        json={
            "expected_revision": revision,
            "analysis_id": analysis_id,
            "recipient_id": recipient_id,
        },
    ).json()["submission_id"]

    submissions = client.get(f"/api/cases/{case_id}").json()["submissions"]

    assert [row["submission_id"] for row in submissions] == [submission_id]
    assert submissions[0]["recipient_id"] == recipient_id
    assert submissions[0]["status"] == SubmissionState.submitted.value
