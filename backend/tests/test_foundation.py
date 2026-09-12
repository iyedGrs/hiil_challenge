"""Foundation slice checks (spec/backend.md B8, B9, B11; spec/local-dev.md L6).

Covers the contract surface this slice owns: health, bootstrap config, the session
and CSRF boundary, and the strict-input error envelope. Deterministic, no network.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.domain.enums import CaseType, Currency, ExecutionMode, LegalCoverage, RequestedOutcome
from app.errors import CSRF_INVALID, INVALID_INPUT, UNAUTHENTICATED
from app.security import hash_password, verify_password
from tests.conftest import DEMO_PASSWORD, DEMO_PREPARER_EMAIL


def login(client: TestClient, email: str = DEMO_PREPARER_EMAIL, password: str = DEMO_PASSWORD):
    """Sign in and return the raw response (spec/backend.md B9)."""
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_health_live_reports_ok(client: TestClient) -> None:
    """``/api/health/live`` answers 200 without touching dependencies."""
    response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_exposes_documented_keys(client: TestClient) -> None:
    """``/api/config`` returns the exact B9 shape and needs no session."""
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "case_types",
        "currencies",
        "requested_outcomes",
        "limits",
        "legal_coverage",
        "execution_mode",
    }
    assert body["case_types"] == [CaseType.unpaid_goods_invoice.value]
    assert body["currencies"] == [Currency.TND.value]
    assert set(body["requested_outcomes"]) == {
        RequestedOutcome.payment.value,
        RequestedOutcome.payment_plan.value,
    }
    assert set(body["limits"]) == {
        "max_case_files",
        "max_case_pages",
        "max_file_bytes",
        "max_case_bytes",
        "supported_mime_types",
    }
    assert body["limits"]["supported_mime_types"] == [
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]
    # No reviewed legal pack is loaded in this slice (spec/backend.md B5).
    assert body["legal_coverage"] == LegalCoverage.unvalidated.value
    assert body["execution_mode"] == ExecutionMode.fixture.value


def test_login_sets_session_cookie_and_returns_csrf_token(
    client: TestClient, seeded: None
) -> None:
    """Login issues an HttpOnly session cookie plus a CSRF token (B8, B9)."""
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == DEMO_PREPARER_EMAIL
    assert body["user"]["role"] == "preparer"
    assert body["csrf_token"]
    assert "password" not in str(body)

    cookie_header = response.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header.replace("samesite", "SameSite")
    assert client.cookies.get(SESSION_COOKIE_NAME)


def test_login_rejects_wrong_password_uniformly(client: TestClient, seeded: None) -> None:
    """Invalid credentials answer 401 with no account disclosure (B9)."""
    wrong_password = login(client, password="not-the-password")
    unknown_account = login(client, email="nobody@demo.local", password=DEMO_PASSWORD)

    assert wrong_password.status_code == 401
    assert unknown_account.status_code == 401
    assert wrong_password.json()["error"]["code"] == UNAUTHENTICATED
    # Identical wording: the response cannot be used to enumerate accounts.
    assert wrong_password.json()["error"]["message"] == unknown_account.json()["error"]["message"]


def test_me_requires_a_session(client: TestClient) -> None:
    """``/api/auth/me`` answers 401 ``UNAUTHENTICATED`` without a cookie (B9)."""
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == UNAUTHENTICATED
    assert error["field_errors"] == []
    assert error["retryable"] is False


def test_me_returns_session_after_login(client: TestClient, seeded: None) -> None:
    """``/api/auth/me`` mirrors the login payload shape (B9)."""
    token = login(client).json()["csrf_token"]

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["csrf_token"] == token
    assert response.json()["user"]["email"] == DEMO_PREPARER_EMAIL


def test_mutation_without_csrf_header_is_rejected(client: TestClient, seeded: None) -> None:
    """An unsafe method without ``X-CSRF-Token`` is refused (B8)."""
    login(client)

    response = client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == CSRF_INVALID
    # The session survives a rejected mutation.
    assert client.get("/api/auth/me").status_code == 200


def test_mutation_with_wrong_csrf_header_is_rejected(client: TestClient, seeded: None) -> None:
    """A mismatched CSRF token is refused as well (B8)."""
    login(client)

    response = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: "not-the-token"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == CSRF_INVALID


def test_logout_revokes_session_and_returns_204(client: TestClient, seeded: None) -> None:
    """Logout answers 204, clears the cookie and invalidates the session (B9)."""
    token = login(client).json()["csrf_token"]

    response = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: token})

    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/auth/me").status_code == 401


def test_unknown_field_on_login_body_returns_invalid_input(client: TestClient) -> None:
    """Unknown fields are rejected with 422 and field errors (B3, B9)."""
    response = client.post(
        "/api/auth/login",
        json={"email": "preparer1@demo.local", "password": "x", "role": "reviewer"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == INVALID_INPUT
    assert error["retryable"] is False
    fields = {entry["field"] for entry in error["field_errors"]}
    assert "body.role" in fields
    # The submitted values are never echoed back (spec/backend.md B9).
    assert "reviewer" not in str(error["field_errors"])


def test_missing_field_on_login_body_returns_field_errors(client: TestClient) -> None:
    """A missing required field is reported per field, not as a generic 500."""
    response = client.post("/api/auth/login", json={"email": "preparer1@demo.local"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == INVALID_INPUT
    assert {entry["field"] for entry in error["field_errors"]} == {"body.password"}


def test_password_hash_is_salted_and_verifiable() -> None:
    """scrypt hashing round-trips and salts per call (spec/backend.md B8)."""
    first = hash_password(DEMO_PASSWORD)
    second = hash_password(DEMO_PASSWORD)

    assert first != second
    assert first.startswith("scrypt$")
    assert DEMO_PASSWORD not in first
    assert verify_password(DEMO_PASSWORD, first)
    assert not verify_password("wrong", first)
    assert not verify_password(DEMO_PASSWORD, "not-a-valid-digest")


def test_seed_is_idempotent(db: Session, seeded: None) -> None:
    """Re-running the seed does not duplicate rows (spec/local-dev.md L4)."""
    from sqlalchemy import func, select

    from app.models.user import Recipient, User
    from app.seed_demo import seed

    before_users = db.scalar(select(func.count()).select_from(User))
    before_recipients = db.scalar(select(func.count()).select_from(Recipient))

    seed(db, password=DEMO_PASSWORD)
    db.commit()

    assert db.scalar(select(func.count()).select_from(User)) == before_users
    assert db.scalar(select(func.count()).select_from(Recipient)) == before_recipients
    assert before_users == 3
    assert before_recipients == 1
