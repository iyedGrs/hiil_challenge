"""Document ingestion slice checks (spec/backend.md B4, B9, B11).

Cases and claim intake belong to a parallel branch (feat/backend-intake), so a
minimal ``Case``/``ClaimRevision`` pair is inserted directly through SQLAlchemy
here rather than through a ``POST /cases`` route -- that route is out of scope
for this slice and deliberately not added.

No network or AI provider call. PDFs are generated in-memory with ReportLab so
the embedded-text path is exercised without any system binary. The OCR path is
covered by mocking ``pytesseract`` so the suite passes even though the
``tesseract`` executable is not installed in this environment.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER_NAME, reset_settings_cache
from app.domain.enums import (
    CaseType,
    ClaimOrigin,
    Currency,
    DocumentState,
    IntakeStatus,
    PageMethod,
    PageState,
    RequestedOutcome,
)
from app.errors import FILE_LIMIT, NOT_FOUND, REVISION_CONFLICT, UNSUPPORTED_FILE
from app.ids import CASE_PREFIX, new_id
from app.models.case import Case, ClaimRevision
from app.models.document import Document, Page
from app.models.user import User
from tests.conftest import DEMO_PASSWORD, DEMO_PREPARER_EMAIL

SECOND_PREPARER_EMAIL = "preparer2@demo.local"

# A long paragraph so embedded-text pages clear the "ready" character threshold.
LONG_PAGE_TEXT = (
    "Facture numero 2026-014. Le fournisseur a livre les marchandises commandees "
    "le 10 juin 2026 et la facture reste impayee a ce jour selon les termes convenus."
)


def login(client: TestClient, email: str = DEMO_PREPARER_EMAIL, password: str = DEMO_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth_headers(client: TestClient, email: str = DEMO_PREPARER_EMAIL) -> dict[str, str]:
    """Log in and return the CSRF header needed for a mutating request."""
    token = login(client, email=email).json()["csrf_token"]
    return {CSRF_HEADER_NAME: token}


def make_case(db: Session, owner: User) -> Case:
    """Insert a minimal Case + ClaimRevision(1) row (see module docstring)."""
    case = Case(
        id=new_id(CASE_PREFIX),
        owner_id=owner.id,
        case_type=CaseType.unpaid_goods_invoice,
        revision=1,
    )
    db.add(case)
    db.flush()

    claim = ClaimRevision(
        case_id=case.id,
        revision=1,
        case_type=CaseType.unpaid_goods_invoice,
        claimant_name="Demo Supplier",
        counterparty_name="Demo Customer",
        claimed_amount=Decimal("20000.000"),
        currency=Currency.TND,
        requested_outcome=RequestedOutcome.payment,
        narrative=(
            "We supplied office furniture and claim that the invoice remains "
            "unpaid despite repeated reminders sent to the counterparty."
        ),
        date_contract=date(2026, 6, 1),
        date_delivery=date(2026, 6, 10),
        date_invoice=date(2026, 6, 10),
        date_payment_due=date(2026, 7, 10),
        follow_up_answers=[],
        claim_json={},
        origin=ClaimOrigin.user_claim,
        intake_status=IntakeStatus.ready,
        intake_questions=[],
        created_by=owner.id,
    )
    db.add(claim)
    db.flush()
    return case


def get_user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def pdf_bytes(page_texts: list[str | None], *, encrypted: bool = False) -> bytes:
    """Build a synthetic multi-page PDF. ``None`` pages have no drawn text."""
    buffer = BytesIO()
    kwargs = {"encrypt": "secret-owner-password"} if encrypted else {}
    pdf_canvas = canvas.Canvas(buffer, pagesize=letter, **kwargs)
    for text in page_texts:
        if text:
            pdf_canvas.drawString(72, 700, text)
        pdf_canvas.showPage()
    pdf_canvas.save()
    return buffer.getvalue()


def png_bytes() -> bytes:
    image = Image.new("RGB", (64, 64), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def case_owner(db: Session, seeded: None) -> tuple[Case, User]:
    owner = get_user(db, DEMO_PREPARER_EMAIL)
    case = make_case(db, owner)
    return case, owner


@pytest.fixture()
def override_settings():
    """Temporarily override a Settings field via env var, then restore it."""
    changed: dict[str, str | None] = {}

    def _set(name: str, value: str) -> None:
        changed[name] = os.environ.get(name)
        os.environ[name] = value
        reset_settings_cache()

    yield _set

    for name, original in changed.items():
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original
    reset_settings_cache()


def test_upload_pdf_creates_ready_pages(
    client: TestClient, db: Session, case_owner: tuple[Case, User]
) -> None:
    """A PDF with real embedded text on every page becomes ``ready`` (B4)."""
    case, _owner = case_owner
    headers = auth_headers(client)
    data = pdf_bytes([LONG_PAGE_TEXT, LONG_PAGE_TEXT])

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", data, "application/pdf")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert body["revision"] == 2
    document = body["document"]
    assert document["state"] == DocumentState.ready.value
    assert document["page_count"] == 2
    assert document["mime_type"] == "application/pdf"
    # The original filename is never used as the storage key.
    assert document["display_name"] == "invoice.pdf"

    pages = db.scalars(
        select(Page).where(Page.document_id == document["id"]).order_by(Page.page_number)
    ).all()
    assert len(pages) == 2
    assert all(page.state == PageState.ready for page in pages)
    assert all(page.method == PageMethod.embedded_text for page in pages)
    assert all(page.text.strip() for page in pages)

    db.refresh(case)
    assert case.revision == 2


def test_duplicate_upload_returns_200_without_revision_bump(
    client: TestClient, db: Session, case_owner: tuple[Case, User]
) -> None:
    """Exact byte-identical re-upload answers 200 duplicate, no new revision (B9)."""
    case, _owner = case_owner
    headers = auth_headers(client)
    data = pdf_bytes([LONG_PAGE_TEXT])

    first = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", data, "application/pdf")},
        data={"expected_revision": "1"},
    )
    assert first.status_code == 201
    revision_after_first = first.json()["revision"]

    second = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice-renamed.pdf", data, "application/pdf")},
        data={"expected_revision": str(revision_after_first)},
    )

    assert second.status_code == 200
    body = second.json()
    assert body["duplicate"] is True
    assert body["revision"] == revision_after_first
    assert body["document"]["id"] == first.json()["document"]["id"]

    db.refresh(case)
    assert case.revision == revision_after_first


def test_stale_expected_revision_returns_409(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    case, _owner = case_owner
    headers = auth_headers(client)

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", pdf_bytes([LONG_PAGE_TEXT]), "application/pdf")},
        data={"expected_revision": "99"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == REVISION_CONFLICT


def test_oversized_file_returns_413(
    client: TestClient, case_owner: tuple[Case, User], override_settings
) -> None:
    """A file over ``max_file_bytes`` is rejected before it is fully parsed (B4)."""
    case, _owner = case_owner
    override_settings("MAX_FILE_BYTES", "1000")
    headers = auth_headers(client)
    data = pdf_bytes([LONG_PAGE_TEXT] * 5)
    assert len(data) > 1000

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", data, "application/pdf")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == FILE_LIMIT


def test_wrong_mime_type_is_rejected_by_content_sniffing(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    """A mislabeled upload is rejected by content signature, not the header (B4)."""
    case, _owner = case_owner
    headers = auth_headers(client)

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        # Plain text renamed with a .pdf name and a spoofed Content-Type.
        files={"file": ("fake.pdf", b"This is not a real PDF file.", "application/pdf")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == UNSUPPORTED_FILE


def test_unsupported_encrypted_file_is_rejected_without_crashing(
    client: TestClient, db: Session, case_owner: tuple[Case, User]
) -> None:
    """An encrypted PDF is stored as a rejected row, not silently dropped (B4)."""
    case, _owner = case_owner
    headers = auth_headers(client)
    data = pdf_bytes([LONG_PAGE_TEXT], encrypted=True)

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("secret.pdf", data, "application/pdf")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == UNSUPPORTED_FILE

    rejected = db.scalar(select(Document).where(Document.case_id == case.id))
    assert rejected is not None
    assert rejected.state == DocumentState.rejected
    assert rejected.is_active is False
    assert rejected.rejection_code is not None
    assert rejected.rejection_message is not None
    # No raw parser traceback or content leaks into the stored message.
    assert "Traceback" not in rejected.rejection_message

    db.refresh(case)
    # A rejected file does not bump the revision or occupy an active-file slot.
    assert case.revision == 1


def test_page_count_over_limit_is_rejected(
    client: TestClient, db: Session, case_owner: tuple[Case, User], override_settings
) -> None:
    """Exceeding the total-page cap rejects the whole upload and stores nothing (B4)."""
    case, _owner = case_owner
    override_settings("MAX_CASE_PAGES", "1")
    headers = auth_headers(client)
    data = pdf_bytes([LONG_PAGE_TEXT, LONG_PAGE_TEXT])

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", data, "application/pdf")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == FILE_LIMIT

    assert db.scalar(select(Document).where(Document.case_id == case.id)) is None
    db.refresh(case)
    assert case.revision == 1


def test_detach_bumps_revision_and_preserves_document_row(
    client: TestClient, db: Session, case_owner: tuple[Case, User]
) -> None:
    case, _owner = case_owner
    headers = auth_headers(client)

    upload = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", pdf_bytes([LONG_PAGE_TEXT]), "application/pdf")},
        data={"expected_revision": "1"},
    )
    document_id = upload.json()["document"]["id"]
    revision_after_upload = upload.json()["revision"]

    response = client.delete(
        f"/api/cases/{case.id}/documents/{document_id}",
        headers=headers,
        params={"expected_revision": revision_after_upload},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == revision_after_upload + 1
    assert body["document"]["is_active"] is False

    row = db.get(Document, document_id)
    assert row is not None
    assert row.is_active is False
    assert row.detached_at is not None
    assert row.detached_revision == revision_after_upload + 1

    db.refresh(case)
    assert case.revision == revision_after_upload + 1


def test_detach_with_stale_revision_returns_409(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    case, _owner = case_owner
    headers = auth_headers(client)
    upload = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", pdf_bytes([LONG_PAGE_TEXT]), "application/pdf")},
        data={"expected_revision": "1"},
    )
    document_id = upload.json()["document"]["id"]

    response = client.delete(
        f"/api/cases/{case.id}/documents/{document_id}",
        headers=headers,
        params={"expected_revision": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == REVISION_CONFLICT


def test_unauthorized_user_gets_404_not_403(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    """A case owned by another preparer answers 404, never 403 (B8, B9)."""
    case, _owner = case_owner
    other_headers = auth_headers(client, email=SECOND_PREPARER_EMAIL)

    upload_response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=other_headers,
        files={"file": ("invoice.pdf", pdf_bytes([LONG_PAGE_TEXT]), "application/pdf")},
        data={"expected_revision": "1"},
    )
    assert upload_response.status_code == 404
    assert upload_response.json()["error"]["code"] == NOT_FOUND

    delete_response = client.delete(
        f"/api/cases/{case.id}/documents/DOC_0000000000",
        headers=other_headers,
        params={"expected_revision": 1},
    )
    assert delete_response.status_code == 404
    assert delete_response.json()["error"]["code"] == NOT_FOUND


def test_content_and_page_routes_are_owner_scoped(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    case, _owner = case_owner
    headers = auth_headers(client)
    upload = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("invoice.pdf", pdf_bytes([LONG_PAGE_TEXT]), "application/pdf")},
        data={"expected_revision": "1"},
    )
    document_id = upload.json()["document"]["id"]

    content_response = client.get(f"/api/documents/{document_id}/content")
    assert content_response.status_code == 200
    assert content_response.headers["content-type"] == "application/pdf"
    assert "inline" in content_response.headers["content-disposition"]

    page_response = client.get(f"/api/documents/{document_id}/pages/1")
    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["page_number"] == 1
    assert page_body["method"] == PageMethod.embedded_text.value
    assert page_body["state"] == PageState.ready.value
    assert LONG_PAGE_TEXT in page_body["text"]

    missing_page_response = client.get(f"/api/documents/{document_id}/pages/99")
    assert missing_page_response.status_code == 404

    # A second preparer cannot read another owner's document (B9).
    other_headers = auth_headers(client, email=SECOND_PREPARER_EMAIL)
    other_content = client.get(
        f"/api/documents/{document_id}/content",
        headers={k: v for k, v in other_headers.items() if k != CSRF_HEADER_NAME},
    )
    assert other_content.status_code == 404


def test_case_revision_increments_across_sequential_uploads(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    case, _owner = case_owner
    headers = auth_headers(client)

    revisions: list[int] = []
    for index in range(3):
        response = client.post(
            f"/api/cases/{case.id}/documents",
            headers=headers,
            files={
                "file": (
                    f"invoice-{index}.pdf",
                    pdf_bytes([f"{LONG_PAGE_TEXT} variant {index}"]),
                    "application/pdf",
                )
            },
            data={"expected_revision": str(revisions[-1] if revisions else 1)},
        )
        assert response.status_code == 201
        revisions.append(response.json()["revision"])

    assert revisions == [2, 3, 4]


def test_image_upload_ocr_path_is_mocked(
    client: TestClient, db: Session, case_owner: tuple[Case, User], monkeypatch
) -> None:
    """OCR is exercised via a mock so the suite does not need Tesseract installed.

    ``pytesseract.image_to_string`` is patched at its ``app.extraction`` import
    site to return deterministic text, proving the OCR code path (method=ocr,
    image storage, quality metadata) works end to end without depending on the
    system binary being present in this environment.
    """
    case, _owner = case_owner
    headers = auth_headers(client)

    monkeypatch.setattr(
        "app.extraction.pytesseract.image_to_string",
        lambda image, lang=None: LONG_PAGE_TEXT,
    )

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("scan.png", png_bytes(), "image/png")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["state"] == DocumentState.ready.value
    assert body["document"]["page_count"] == 1

    page = db.scalar(select(Page).where(Page.document_id == body["document"]["id"]))
    assert page is not None
    assert page.method == PageMethod.ocr
    assert page.state == PageState.ready
    assert page.image_key is not None
    assert page.quality["source"] == "ocr"


@pytest.mark.skipif(
    os.environ.get("SKIP_REAL_TESSERACT_TEST", "1") == "1",
    reason="Real Tesseract binary not guaranteed in this dev environment; "
    "set SKIP_REAL_TESSERACT_TEST=0 to run against a real install.",
)
def test_image_upload_real_ocr_when_tesseract_available(
    client: TestClient, case_owner: tuple[Case, User]
) -> None:
    """Optional: exercises the real Tesseract binary when explicitly enabled."""
    case, _owner = case_owner
    headers = auth_headers(client)

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("scan.png", png_bytes(), "image/png")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 201
    assert response.json()["document"]["state"] in {
        DocumentState.ready.value,
        DocumentState.partial.value,
        DocumentState.unreadable.value,
    }


def test_ocr_missing_binary_marks_page_unreadable_not_crashed(
    client: TestClient, db: Session, case_owner: tuple[Case, User]
) -> None:
    """Without a real Tesseract install the scan page degrades to unreadable (B4).

    This runs against the real (missing) binary in this dev environment and
    asserts the request still succeeds rather than raising.
    """
    case, _owner = case_owner
    headers = auth_headers(client)

    response = client.post(
        f"/api/cases/{case.id}/documents",
        headers=headers,
        files={"file": ("scan.png", png_bytes(), "image/png")},
        data={"expected_revision": "1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["state"] == DocumentState.unreadable.value

    page = db.scalar(select(Page).where(Page.document_id == body["document"]["id"]))
    assert page is not None
    assert page.state == PageState.unreadable
    assert page.quality.get("ocr_error") == "TesseractNotFoundError"
