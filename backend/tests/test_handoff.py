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
import zipfile

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER_NAME
from app.domain.enums import AnalysisStatus, CheckResult, ExecutionMode, ExportState, JobStatus, SubmissionState
from app.files import sha256_hex
from app.models.analysis import Analysis, CheckResultRow
from app.models.document import Document
from app.models.job import Job
from app.models.submission import Export
from app.pipeline.export import (
    date_fact_kind_for_document_type,
    handle_export_job,
    reference_fact_kind_for_document_type,
    sanitize_case_reference,
    sanitize_piece_filename,
    select_fact_value,
)
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


def _pdf_text(data: bytes) -> str:
    """Extract plain text from PDF ``data`` for content assertions."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

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


EXPECTED_TOP_LEVEL_PDFS = (
    "01_requete_introductive_instance.pdf",
    "02_bordereau_des_pieces.pdf",
    "03_resume_verification.pdf",
)


def test_export_produces_a_real_package_with_disclosures(
    client: TestClient, db: Session, seeded: None
) -> None:
    """B10: one ZIP with the claim, bordereau, summary and the original pieces."""
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

    # Disclosures travel with the export even though no manifest.json ships in
    # the ZIP: the record is kept internally on export.manifest (B10).
    assert export.manifest["legal_coverage"] == "unvalidated"
    assert export.manifest["claim_is_an_allegation"] is True
    assert "No legal advice" in export.manifest["notice"]

    content = client.get(f"/api/exports/{export_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "application/zip"
    assert (
        content.headers["content-disposition"]
        == f'attachment; filename="e-ethbet-dossier-{case_id}.zip"'
    )

    active_documents = list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case_id, Document.is_active.is_(True))
            .order_by(Document.created_at, Document.id)
        ).all()
    )

    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        names = archive.namelist()
        piece_names = sorted(name for name in names if name.startswith("pieces/"))

        # Exactly the 3 PDFs plus one piece per active document, nothing else.
        assert sorted(names) == sorted(list(EXPECTED_TOP_LEVEL_PDFS) + piece_names)
        assert not any(name.lower().endswith(".json") for name in names)
        assert len(piece_names) == len(active_documents)
        assert all(name.startswith("pieces/") for name in names if name not in EXPECTED_TOP_LEVEL_PDFS)

        for pdf_name in EXPECTED_TOP_LEVEL_PDFS:
            data = archive.read(pdf_name)
            assert data.startswith(b"%PDF")
            assert len(data) > 1000
            # Header and page numbering are drawn on every page.
            text = _pdf_text(data)
            assert f"e-ethbet — {case_id}" in text
            assert "Page 1 / " in text

        claim_text = _pdf_text(archive.read("01_requete_introductive_instance.pdf"))
        assert "REQUÊTE INTRODUCTIVE D’INSTANCE" in claim_text
        assert "BORDEREAU DES PIÈCES" in _pdf_text(archive.read("02_bordereau_des_pieces.pdf"))

        # Every active document appears exactly once, in upload order, with the
        # exact stored bytes.
        expected_order = [
            f"pieces/P{index:02d}_" for index in range(1, len(active_documents) + 1)
        ]
        for prefix, document in zip(expected_order, active_documents, strict=True):
            matches = [name for name in piece_names if name.startswith(prefix)]
            assert len(matches) == 1
            data = archive.read(matches[0])
            assert sha256_hex(data) == document.sha256


def test_export_numbering_matches_across_claim_and_bordereau(
    client: TestClient, db: Session, seeded: None
) -> None:
    """Piece numbering is computed once and shared by every rendered document."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-numbering"},
        json={"expected_revision": revision, "analysis_id": analysis_id, "acknowledge_unresolved": True},
    )
    run_export_job(client, db, started.json()["job_id"])
    content = client.get(f"/api/exports/{started.json()['export_id']}/content")

    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        piece_names = sorted(name for name in archive.namelist() if name.startswith("pieces/"))
        bordereau_text = _pdf_text(archive.read("02_bordereau_des_pieces.pdf"))
        claim_text = _pdf_text(archive.read("01_requete_introductive_instance.pdf"))

    for piece_name in piece_names:
        # e.g. "pieces/P01_facture.pdf" -> "P01_facture.pdf"
        filename = piece_name.split("pieces/", 1)[1]
        assert filename in bordereau_text
    assert "P01" in claim_text


def test_export_fails_when_an_original_is_missing(
    client: TestClient, db: Session, seeded: None
) -> None:
    """A missing original never produces a partial package (B10)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    document = db.scalar(select(Document).where(Document.case_id == case_id))
    assert document is not None

    from app.config import get_settings
    from app.files import storage_path

    path = storage_path(get_settings().file_storage_root, document.storage_key)
    path.unlink()

    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-missing"},
        json={"expected_revision": revision, "analysis_id": analysis_id, "acknowledge_unresolved": True},
    )
    # handle_export_job re-raises after marking the export failed (mirrors
    # app/worker.py, which catches this at the job-loop level).
    from app.errors import ApiError

    with pytest.raises(ApiError):
        run_export_job(client, db, started.json()["job_id"])

    export = db.get(Export, started.json()["export_id"])
    assert export is not None
    assert export.state is ExportState.failed

    content = client.get(f"/api/exports/{started.json()['export_id']}/content")
    assert content.status_code == 409


def test_export_amounts_reflect_stored_reconciliation(
    client: TestClient, db: Session, seeded: None
) -> None:
    """Amounts in the claim PDF come only from the stored reconciliation (B7)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    analysis = db.get(Analysis, analysis_id)
    assert analysis is not None

    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-amounts"},
        json={"expected_revision": revision, "analysis_id": analysis_id, "acknowledge_unresolved": True},
    )
    run_export_job(client, db, started.json()["job_id"])
    content = client.get(f"/api/exports/{started.json()['export_id']}/content")
    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        claim_text = _pdf_text(archive.read("01_requete_introductive_instance.pdf"))

    assert "20000.000" in claim_text
    if analysis.reconciliation:
        balance = str(analysis.reconciliation["documented_balance"])
        assert balance in claim_text
    else:  # pragma: no cover - depends on fixture data shape
        assert "Non renseign" in claim_text


def test_export_with_no_reconciliation_shows_non_renseigne(
    client: TestClient, db: Session, seeded: None
) -> None:
    """No stored reconciliation -> the balance row reads "Non renseigné"."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    analysis = db.get(Analysis, analysis_id)
    assert analysis is not None
    analysis.reconciliation = None
    db.commit()

    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-no-reco"},
        json={"expected_revision": revision, "analysis_id": analysis_id, "acknowledge_unresolved": True},
    )
    run_export_job(client, db, started.json()["job_id"])
    content = client.get(f"/api/exports/{started.json()['export_id']}/content")
    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        claim_text = _pdf_text(archive.read("01_requete_introductive_instance.pdf"))

    assert "renseign" in claim_text.lower()  # "Non renseigné"
    assert "Aucun rapprochement" in claim_text


def test_export_missing_info_uses_placeholders(
    client: TestClient, db: Session, seeded: None
) -> None:
    """No court/lawyer data exists, so the claim PDF says so explicitly (never invented)."""
    case_id, revision, analysis_id, headers = prepared_case(client, db)
    started = client.post(
        f"/api/cases/{case_id}/exports",
        headers={**headers, "Idempotency-Key": "export-placeholders"},
        json={"expected_revision": revision, "analysis_id": analysis_id, "acknowledge_unresolved": True},
    )
    run_export_job(client, db, started.json()["job_id"])
    content = client.get(f"/api/exports/{started.json()['export_id']}/content")
    with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
        claim_text = _pdf_text(archive.read("01_requete_introductive_instance.pdf"))
        bordereau_text = _pdf_text(archive.read("02_bordereau_des_pieces.pdf"))

    assert "compl" in claim_text.lower()  # "À compléter" (tribunal, fondement juridique)
    assert claim_text.lower().count("compl") >= 2
    assert "renseign" in bordereau_text.lower()  # "Non renseigné" on at least one row


@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("../../etc/passwd", ("..", "/", "\\")),
        ("..\\..\\x.pdf", ("..", "/", "\\")),
        ("a/b/c.pdf", ("/", "\\")),
        ("  .hidden.pdf", ()),
        ("facture été.pdf", ()),
    ],
)
def test_sanitize_piece_filename_blocks_path_traversal(raw: str, forbidden: tuple[str, ...]) -> None:
    """B10: a client filename can never escape the ``pieces/`` directory."""
    safe = sanitize_piece_filename(raw)
    for token in forbidden:
        assert token not in safe
    assert safe, "sanitization must never produce an empty name"
    if raw.endswith(".pdf"):
        assert safe.endswith(".pdf")


def test_sanitize_piece_filename_falls_back_to_document() -> None:
    assert sanitize_piece_filename("") == "document"
    assert sanitize_piece_filename("...") == "document"


def test_sanitize_case_reference_strips_unsafe_characters() -> None:
    assert sanitize_case_reference("CASE_abc-123") == "CASE_abc-123"
    assert sanitize_case_reference("CASE/abc?123") == "CASE_abc_123"


def test_reference_and_date_selection_never_borrow_the_wrong_kind() -> None:
    """A delivery note carrying only an invoice_number must show Non renseigné,
    never the invoice's own reference (spec export)."""
    from app.ai.contracts import FactKind

    class _StubFact:
        def __init__(self, document_id: str, kind: str, value_text: str, page: int, created_at: int, id: str) -> None:
            self.document_id = document_id
            self.kind = kind
            self.value_text = value_text
            self.page = page
            self.created_at = created_at
            self.id = id

    facts = [_StubFact("DOC_dn", FactKind.invoice_number.value, "2026-014", 1, 0, "f1")]

    # delivery_note has no reference fact kind at all.
    assert reference_fact_kind_for_document_type("delivery_note") is None
    assert (
        select_fact_value(facts, document_id="DOC_dn", kind=reference_fact_kind_for_document_type("delivery_note"))
        is None
    )
    # And it must not accidentally match the invoice kind either.
    assert select_fact_value(facts, document_id="DOC_dn", kind="order_reference") is None
    # Nor does it have a date fact kind.
    assert date_fact_kind_for_document_type("delivery_note") == FactKind.delivery_date.value


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
