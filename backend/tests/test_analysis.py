"""End-to-end analysis pipeline checks (spec/backend.md B6, B7, B11).

Walks the P6 demo path with synthetic PDFs and asserts the acceptance criteria the
pipeline is responsible for:

* **BE-03** - a missing supported item is found, and acceptable evidence later
  satisfies the same check.
* **BE-04** - every published fact carries validated in-case page/quote provenance.
* **BE-07** - the balance is computed by ``Decimal`` code: 20 000 less 5 000 is
  15 000 TND, and the claim discrepancy is flagged.
* **BE-08** - the same payment appearing in a receipt and a bank statement is not
  counted twice.
* **BE-10** - reassessment preserves check/subject identity and reports a real
  delta.
* **BE-11** - a revision change while a run is in flight supersedes it.

``AI_MODE`` is ``fixture`` in the test environment, so the whole run is
deterministic and makes no network call. The job is executed inline by calling the
worker handler directly, which keeps the test synchronous while still going through
the real handler, validators and publication path.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER_NAME
from app.domain.enums import (
    AnalysisStatus,
    CheckResult,
    Delta,
    FactVerification,
    FindingStatus,
    JobStatus,
    ReasonCode,
)
from app.models.case import Case
from app.models.fact import Fact
from app.models.job import Job
from app.models.subject import Subject
from app.pipeline.analysis import handle_analysis_job
from tests.conftest import DEMO_PASSWORD, DEMO_PREPARER_EMAIL

# Deliberately unaccented so the assertions do not depend on how the PDF font and
# the text extractor round-trip accents.
INVOICE_LINES = [
    "SOCIETE DEMO SUPPLIER - Facture",
    "Facture no 2026-014 du 10 juin 2026",
    "Client : Demo Customer, Tunis",
    "Fourniture de mobilier de bureau selon bon de commande BC-2026-77",
    "Total HT : 16 800,000 TND",
    "Total TTC : 20 000,000 TND",
    "Date de facture : 2026-06-10",
]

DELIVERY_LINES = [
    "BON DE LIVRAISON no BL-2026-31",
    "Client : Demo Customer, Tunis",
    "Marchandises livrees et recues en bon etat le 10 juin 2026",
    "Reference commande : BC-2026-77",
    "Signature du client : cachet appose",
]

RECEIPT_LINES = [
    "RECU DE PAIEMENT",
    "Paiement recu par virement bancaire",
    "Reference virement : VIR-889021",
    "Montant : 5 000,000 TND",
    "Date de paiement : 2026-07-15",
]

# Same 5 000,000 payment, same reference, seen again in a bank statement. It must
# not be counted a second time (BE-08).
STATEMENT_LINES = [
    "RELEVE BANCAIRE - juillet 2026",
    "Compte : TN59 0000 1111 2222 3333",
    "Virement recu reference VIR-889021",
    "Montant : 5 000,000 TND",
]

READY_CLAIM: dict[str, object] = {
    "case_type": "unpaid_goods_invoice",
    "claimant_name": "Demo Supplier",
    "counterparty_name": "Demo Customer",
    "claimed_amount": "20000.000",
    "currency": "TND",
    "dates": {
        "contract": "2026-06-01",
        "delivery": "2026-06-10",
        "invoice": "2026-06-10",
        "payment_due": "2026-07-10",
    },
    "requested_outcome": "payment",
    "narrative": (
        "We supplied office furniture to the customer on 10 June 2026 and issued "
        "invoice 2026-014. The invoice remains unpaid despite two reminders."
    ),
    "follow_up_answers": [],
}


def pdf_bytes(lines: list[str]) -> bytes:
    """Render ``lines`` as a one-page PDF with real embedded text."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    y = 720
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def auth_headers(client: TestClient) -> dict[str, str]:
    token = client.post(
        "/api/auth/login", json={"email": DEMO_PREPARER_EMAIL, "password": DEMO_PASSWORD}
    ).json()["csrf_token"]
    return {CSRF_HEADER_NAME: token}


def upload(
    client: TestClient, headers: dict[str, str], case_id: str, revision: int, name: str, lines: list[str]
) -> int:
    """Upload one PDF and return the new case revision."""
    response = client.post(
        f"/api/cases/{case_id}/documents",
        headers=headers,
        files={"file": (name, pdf_bytes(lines), "application/pdf")},
        data={"expected_revision": str(revision)},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["revision"])


def run_analysis(client: TestClient, db: Session, headers: dict[str, str], case_id: str, revision: int) -> dict:
    """Queue an analysis, execute the handler inline and return the published run."""
    started = client.post(
        f"/api/cases/{case_id}/analyses",
        headers={**headers, "Idempotency-Key": f"test-{case_id}-{revision}"},
        json={"expected_revision": revision},
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]

    job = db.get(Job, job_id)
    assert job is not None
    job.status = JobStatus.running
    job.lease_owner = "inline-test"
    db.flush()

    handle_analysis_job(db, job)
    # Mirror what the worker loop does after a handler returns, so the case's
    # single assessment slot is released for the next run (app/worker.py).
    if job.status is JobStatus.running:
        job.status = JobStatus.succeeded
        job.phase = None
        job.lease_owner = None
    db.commit()

    polled = client.get(f"/api/jobs/{job_id}").json()
    assert polled["result_analysis_id"], polled
    analysis = client.get(f"/api/analyses/{polled['result_analysis_id']}")
    assert analysis.status_code == 200, analysis.text
    return analysis.json()


def checks_by_id(analysis: dict) -> dict[str, dict]:
    return {check["check_id"]: check for check in analysis["checks"]}


def test_first_run_finds_missing_delivery_evidence(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-03/BE-04: the gap is reported, and what was found carries provenance."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)

    analysis = run_analysis(client, db, headers, case_id, revision)
    checks = checks_by_id(analysis)

    assert analysis["status"] == AnalysisStatus.ready.value
    assert analysis["execution_mode"] == "fixture"
    assert analysis["legal_coverage"] == "unvalidated"

    # The invoice itself was read, with a real quote from a real page.
    invoice = checks["invoice_issued"]
    assert invoice["result"] == CheckResult.satisfied.value
    assert invoice["reason_code"] == ReasonCode.EVIDENCE_FOUND.value
    assert invoice["evidence_refs"], "a satisfied check must cite supporting evidence"
    ref = invoice["evidence_refs"][0]
    assert ref["page"] == 1
    assert ref["document_id"].startswith("DOC_")
    assert ref["source_text"].strip()

    # Delivery evidence is missing and is reported as an open finding.
    delivery = checks["delivery_evidence"]
    assert delivery["result"] == CheckResult.unassessable.value
    assert delivery["reason_code"] == ReasonCode.EVIDENCE_NOT_FOUND.value
    assert delivery["finding_status"] == FindingStatus.open.value
    assert delivery["delta"] == Delta.new.value
    assert delivery["evidence_refs"] == []
    assert "add_evidence" in delivery["actions"]
    assert delivery["legal_reference_ids"] == []
    assert delivery["subject_label"]

    # No payment evidence yet either.
    assert checks["payment_or_credit_note_evidence"]["result"] == CheckResult.unassessable.value


def test_published_facts_all_have_validated_provenance(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-04: every verified fact's quote was located in its own stored page text."""
    from app.models.document import Page
    from app.normalization import quote_matches_page

    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)
    run_analysis(client, db, headers, case_id, revision)

    facts = list(
        db.scalars(
            select(Fact).where(
                Fact.case_id == case_id, Fact.verification == FactVerification.verified
            )
        ).all()
    )
    assert facts, "the invoice should have produced at least one verified fact"
    for fact in facts:
        page = db.scalar(
            select(Page).where(Page.document_id == fact.document_id, Page.page_number == fact.page)
        )
        assert page is not None, "a verified fact must point at a page of the case"
        assert quote_matches_page(fact.source_text, page.text)


def test_correction_loop_resolves_the_finding_and_reconciles_the_balance(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-03/BE-07/BE-10: the P6 demo path, end to end."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)

    first = run_analysis(client, db, headers, case_id, revision)
    first_checks = checks_by_id(first)
    delivery_finding_id = first_checks["delivery_evidence"]["finding_id"]
    assert delivery_finding_id

    # The claim matches the invoice while nothing has been paid yet.
    assert first["reconciliation"] is not None
    assert first["reconciliation"]["documented_balance"] == "20000.000"
    assert first_checks["claim_amount_matches_records"]["result"] == CheckResult.satisfied.value

    # The preparer adds the delivery note and the payment receipt.
    revision = upload(client, headers, case_id, revision, "livraison.pdf", DELIVERY_LINES)
    revision = upload(client, headers, case_id, revision, "recu.pdf", RECEIPT_LINES)

    second = run_analysis(client, db, headers, case_id, revision)
    second_checks = checks_by_id(second)

    # BE-10: same finding identity, and the change is reported as a resolution.
    delivery = second_checks["delivery_evidence"]
    assert delivery["finding_id"] == delivery_finding_id
    assert delivery["result"] == CheckResult.satisfied.value
    assert delivery["finding_status"] == FindingStatus.resolved.value
    assert delivery["delta"] == Delta.resolved.value
    assert delivery["evidence_refs"], "the resolution must cite the new evidence"

    assert second_checks["payment_or_credit_note_evidence"]["result"] == CheckResult.satisfied.value

    # BE-07: 20 000 - 5 000 = 15 000, computed by Decimal code, and the claim of
    # 20 000 is flagged as differing from the documented records.
    reconciliation = second["reconciliation"]
    assert reconciliation is not None
    assert reconciliation["documented_balance"] == "15000.000"
    assert reconciliation["currency"] == "TND"
    assert reconciliation["source_fact_ids"]
    assert "documents deposes" in reconciliation["coverage_note"].replace("é", "e").replace("ô", "o")

    discrepancy = second_checks["claim_amount_matches_records"]
    assert discrepancy["result"] == CheckResult.contradicted.value
    assert discrepancy["reason_code"] == ReasonCode.CONFLICT.value
    assert discrepancy["finding_status"] == FindingStatus.open.value
    assert discrepancy["basis"] == "reconciliation"
    assert "15000.000" in discrepancy["message"]
    assert "20000.000" in discrepancy["message"]


def test_same_payment_in_receipt_and_statement_is_counted_once(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-08: a receipt and a bank statement for one transfer produce one payment."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)
    revision = upload(client, headers, case_id, revision, "recu.pdf", RECEIPT_LINES)
    revision = upload(client, headers, case_id, revision, "releve.pdf", STATEMENT_LINES)

    analysis = run_analysis(client, db, headers, case_id, revision)

    # One payment subject, not two, and the balance reflects a single 5 000.
    payments = list(
        db.scalars(
            select(Subject).where(Subject.case_id == case_id, Subject.subject_type == "payment")
        ).all()
    )
    assert len(payments) == 1, [subject.subject_id for subject in payments]
    assert analysis["reconciliation"]["documented_balance"] == "15000.000"


def test_revision_change_during_a_run_supersedes_it(
    client: TestClient, db: Session, seeded: None
) -> None:
    """BE-11: a run pinned to an old revision cannot publish (spec/backend.md B7)."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)

    started = client.post(
        f"/api/cases/{case_id}/analyses",
        headers=headers,
        json={"expected_revision": revision},
    )
    job_id = started.json()["job_id"]

    # The working case moves on before the worker gets to it.
    upload(client, headers, case_id, revision, "livraison.pdf", DELIVERY_LINES)

    job = db.get(Job, job_id)
    assert job is not None
    job.status = JobStatus.running
    job.lease_owner = "inline-test"
    db.flush()
    handle_analysis_job(db, job)
    db.commit()

    polled = client.get(f"/api/jobs/{job_id}").json()
    assert polled["status"] == JobStatus.superseded.value
    assert polled["result_analysis_id"] is None


def test_second_run_reuses_cached_extraction(client: TestClient, db: Session, seeded: None) -> None:
    """BE-11: unchanged files are not extracted twice (spec/backend.md B6)."""
    from app.models.fact import Extraction

    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)
    run_analysis(client, db, headers, case_id, revision)
    after_first = db.scalar(
        select(Extraction).where(Extraction.case_id == case_id)
    )
    assert after_first is not None

    # A new revision that does not change the invoice file.
    revision = upload(client, headers, case_id, revision, "livraison.pdf", DELIVERY_LINES)
    run_analysis(client, db, headers, case_id, revision)

    extractions = list(db.scalars(select(Extraction).where(Extraction.case_id == case_id)).all())
    # One per distinct document, not one per run.
    assert len(extractions) == 2


def test_analysis_requires_a_ready_intake_gate(client: TestClient, seeded: None) -> None:
    """A non-ready gate answers 409 with the saved questions (spec/backend.md B9)."""
    headers = auth_headers(client)
    vague = {**READY_CLAIM, "narrative": "Le client ne paie pas ce qu'il doit depuis longtemps."}
    created = client.post("/api/cases", json=vague, headers=headers).json()

    response = client.post(
        f"/api/cases/{created['case_id']}/analyses",
        headers=headers,
        json={"expected_revision": 1},
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INTAKE_NOT_READY"
    assert error["field_errors"], "the saved follow-up questions travel with the 409"


def test_one_active_assessment_per_case(client: TestClient, db: Session, seeded: None) -> None:
    """A second concurrent assessment is refused (spec/backend.md B8)."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)

    first = client.post(
        f"/api/cases/{case_id}/analyses", headers=headers, json={"expected_revision": revision}
    )
    assert first.status_code == 202

    second = client.post(
        f"/api/cases/{case_id}/analyses", headers=headers, json={"expected_revision": revision}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ANALYSIS_ALREADY_RUNNING"


def test_idempotent_start_returns_the_same_job(client: TestClient, seeded: None) -> None:
    """Replaying the idempotency key does not launch a second run (B8)."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]

    first = client.post(
        f"/api/cases/{case_id}/analyses",
        headers={**headers, "Idempotency-Key": "same-key"},
        json={"expected_revision": 1},
    )
    second = client.post(
        f"/api/cases/{case_id}/analyses",
        headers={**headers, "Idempotency-Key": "same-key"},
        json={"expected_revision": 1},
    )

    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]


def test_finding_response_bumps_revision_without_resolving(
    client: TestClient, db: Session, seeded: None
) -> None:
    """FE-06/BE-14: a response is recorded, and it does not resolve the finding."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    revision = upload(client, headers, case_id, 1, "facture.pdf", INVOICE_LINES)
    analysis = run_analysis(client, db, headers, case_id, revision)
    delivery = checks_by_id(analysis)["delivery_evidence"]

    response = client.post(
        f"/api/findings/{delivery['finding_id']}/responses",
        headers=headers,
        json={
            "expected_revision": revision,
            "action": "explain_unavailable",
            "explanation": "Le bon de livraison a ete perdu par le transporteur.",
            "document_ids": [],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["revision"] == revision + 1
    assert body["response"]["action"] == "explain_unavailable"

    # The finding is still open: only a validated assessment may change that.
    case = db.get(Case, case_id)
    assert case is not None and case.revision == revision + 1
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["responses"][0]["finding_id"] == delivery["finding_id"]
    assert detail["latest_analysis"]["checks"], "the previous run is still readable"
    still_open = checks_by_id(detail["latest_analysis"])["delivery_evidence"]
    assert still_open["finding_status"] == FindingStatus.open.value


def test_ambiguous_amount_is_not_reconciled(client: TestClient, db: Session, seeded: None) -> None:
    """BE-06: an ambiguous decimal token blocks reconciliation instead of guessing."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    ambiguous = [
        "SOCIETE DEMO SUPPLIER - Facture",
        "Facture no 2026-015 du 10 juin 2026",
        "Fourniture de mobilier de bureau pour le client Demo Customer",
        # "1,000" could be one thousand or one unit and three decimals.
        "Total TTC : 1,000 TND",
    ]
    revision = upload(client, headers, case_id, 1, "facture-ambigue.pdf", ambiguous)

    analysis = run_analysis(client, db, headers, case_id, revision)

    assert analysis["reconciliation"] is None
    check = checks_by_id(analysis)["claim_amount_matches_records"]
    assert check["result"] == CheckResult.unassessable.value
    assert check["reason_code"] == ReasonCode.AMBIGUOUS_LINK.value

    # The literal text is kept; only the resolved value is withheld.
    fact = db.scalar(
        select(Fact).where(Fact.case_id == case_id, Fact.kind == "invoice_total")
    )
    assert fact is not None
    assert fact.value_text == "1,000"
    assert fact.normalized_value is None


def test_decimal_arithmetic_is_exact() -> None:
    """BE-07: the balance is Decimal arithmetic, not float arithmetic."""
    from app.pipeline.reconcile import reconcile

    class _StubFact:
        def __init__(self, kind: str, value: str, subject_id: str, fact_id: str) -> None:
            self.kind = kind
            self.normalized_value = Decimal(value)
            self.subject_id = subject_id
            self.id = fact_id
            self.currency_text = "TND"

    class _StubSubject:
        linkage_confirmed = True

    outcome = reconcile(
        claimed_amount=Decimal("20000.000"),
        currency="TND",
        verified_facts=[
            _StubFact("invoice_total", "20000.000", "invoice_0001", "FACT_a"),
            _StubFact("payment_amount", "5000.000", "payment_0001", "FACT_b"),
        ],  # type: ignore[arg-type]
        subjects_by_id={"payment_0001": _StubSubject()},  # type: ignore[arg-type]
    )

    assert outcome.payload is not None
    assert outcome.payload["documented_balance"] == "15000.000"
    assert outcome.result == CheckResult.contradicted
