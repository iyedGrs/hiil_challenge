"""Case and intake-gate route checks (spec/backend.md B3, B9, B11).

Covers the acceptance criteria this slice is responsible for:

* **BE-01** - an unsupported case type or invalid structured input is rejected
  with zero model calls. There is no provider configured in fixture mode, so any
  such call would fail loudly rather than pass silently.
* **BE-02** - an under-specified claim returns targeted questions *and* keeps the
  draft, so nothing the preparer typed is discarded.

Plus the concurrency rule every mutating route shares: a stale
``expected_revision`` is rejected with 409.

No network or AI provider call.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import CSRF_HEADER_NAME
from app.domain.enums import IntakeStatus
from app.errors import INVALID_INPUT, REVISION_CONFLICT, UNSUPPORTED_CASE_TYPE
from tests.conftest import DEMO_PASSWORD, DEMO_PREPARER_EMAIL

SECOND_PREPARER_EMAIL = "preparer2@demo.local"

#: A narrative that satisfies the gate: it names the goods and the payment issue.
READY_NARRATIVE = (
    "We supplied office furniture to the customer on 10 June 2026 and issued "
    "invoice 2026-014. The invoice remains unpaid despite two reminders."
)

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
    "narrative": READY_NARRATIVE,
    "follow_up_answers": [],
}


def auth_headers(client: TestClient, email: str = DEMO_PREPARER_EMAIL) -> dict[str, str]:
    token = client.post(
        "/api/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    ).json()["csrf_token"]
    return {CSRF_HEADER_NAME: token}


def claim_with(**overrides: object) -> dict[str, object]:
    """Return the ready claim with ``overrides`` applied."""
    return {**READY_CLAIM, **overrides}


def test_create_case_with_sufficient_claim_is_ready(client: TestClient, seeded: None) -> None:
    """A complete, specific claim passes the gate at revision 1 (B3)."""
    headers = auth_headers(client)

    response = client.post("/api/cases", json=READY_CLAIM, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["revision"] == 1
    assert body["intake"]["status"] == IntakeStatus.ready.value
    assert body["intake"]["questions"] == []
    assert body["case_id"].startswith("CASE_")


def test_unsupported_case_type_is_rejected(client: TestClient, seeded: None) -> None:
    """BE-01: an unknown category is a 422 enum error, with no fallback."""
    headers = auth_headers(client)

    response = client.post(
        "/api/cases", json=claim_with(case_type="unpaid_services_invoice"), headers=headers
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == INVALID_INPUT
    assert "case_type" in {entry["field"] for entry in error["field_errors"]}


def test_float_amount_and_extra_field_are_rejected(client: TestClient, seeded: None) -> None:
    """BE-01: a JSON float amount and an unknown field both fail validation (B3)."""
    headers = auth_headers(client)

    float_amount = client.post("/api/cases", json=claim_with(claimed_amount=20000.5), headers=headers)
    assert float_amount.status_code == 422

    extra_field = client.post(
        "/api/cases", json={**READY_CLAIM, "liability": "counterparty"}, headers=headers
    )
    assert extra_field.status_code == 422
    assert "liability" in {
        entry["field"] for entry in extra_field.json()["error"]["field_errors"]
    }


def test_grouped_amount_string_is_rejected_as_non_canonical(
    client: TestClient, seeded: None
) -> None:
    """``20 000,000`` is not a canonical claim amount; the client must normalize it."""
    headers = auth_headers(client)

    response = client.post("/api/cases", json=claim_with(claimed_amount="20 000,000"), headers=headers)

    assert response.status_code == 422
    assert "claimed_amount" in {
        entry["field"] for entry in response.json()["error"]["field_errors"]
    }


def test_under_specified_claim_returns_questions_and_keeps_draft(
    client: TestClient, seeded: None
) -> None:
    """BE-02: the case is still created and the typed claim is preserved (B3, FE-02)."""
    headers = auth_headers(client)
    vague = claim_with(
        narrative="Le client ne veut pas regler ce que nous reclamons depuis un moment."
    )

    response = client.post("/api/cases", json=vague, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["intake"]["status"] == IntakeStatus.needs_information.value
    questions = body["intake"]["questions"]
    assert questions, "an under-specified claim must come back with targeted questions"
    assert len(questions) <= 5
    # Every question is anchored to a claim input the UI can render it next to.
    assert {question["field"] for question in questions} <= {
        "narrative",
        "claimed_amount",
        "dates.invoice",
    }

    # The draft survived: nothing the preparer typed was discarded.
    detail = client.get(f"/api/cases/{body['case_id']}").json()
    assert detail["claim"]["narrative"] == vague["narrative"]
    assert detail["claim"]["claimed_amount"] == "20000.000"
    assert detail["intake"]["status"] == IntakeStatus.needs_information.value


def test_patch_claim_creates_new_revision_and_can_reach_ready(
    client: TestClient, seeded: None
) -> None:
    """A corrected claim becomes a new revision and is re-gated (B3, B9)."""
    headers = auth_headers(client)
    created = client.post(
        "/api/cases", json=claim_with(narrative="Litige commercial en cours avec ce client."), headers=headers
    ).json()
    case_id = created["case_id"]
    assert created["intake"]["status"] == IntakeStatus.needs_information.value

    response = client.patch(
        f"/api/cases/{case_id}/claim",
        json={"expected_revision": 1, "claim": READY_CLAIM},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert body["intake"]["status"] == IntakeStatus.ready.value
    assert body["claim"]["narrative"] == READY_NARRATIVE


def test_patch_claim_with_stale_revision_returns_409(client: TestClient, seeded: None) -> None:
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]

    response = client.patch(
        f"/api/cases/{case_id}/claim",
        json={"expected_revision": 99, "claim": READY_CLAIM},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == REVISION_CONFLICT


def test_patching_with_the_same_case_type_is_allowed(client: TestClient, seeded: None) -> None:
    """Re-sending the same case type is a normal edit (spec/backend.md B9).

    The refusal branch in the handler (``UNSUPPORTED_CASE_TYPE`` when the type
    changes) cannot be reached through the API while exactly one category is
    supported: any other value fails enum validation first. It is asserted
    directly against the handler instead of through a request.
    """
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]

    response = client.patch(
        f"/api/cases/{case_id}/claim",
        json={"expected_revision": 1, "claim": READY_CLAIM},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 2


def test_case_type_change_is_refused_by_the_handler(client: TestClient, db, seeded: None) -> None:
    """A case type switch is refused because it would repoint the checklist (B5)."""
    import pytest

    from app.api.cases import update_claim
    from app.domain.enums import CaseType
    from app.errors import ApiError
    from app.models.case import Case
    from app.models.user import User
    from app.schemas.cases import ClaimIn, PatchClaimIn
    from sqlalchemy import select

    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]
    owner = db.scalar(select(User).where(User.email == DEMO_PREPARER_EMAIL))
    case = db.get(Case, case_id)
    assert case is not None and owner is not None

    # Simulate a second supported category by moving the stored case off the
    # type the incoming claim carries.
    case.case_type = CaseType.unpaid_goods_invoice
    payload = PatchClaimIn(expected_revision=1, claim=ClaimIn.model_validate(READY_CLAIM))
    object.__setattr__(payload.claim, "case_type", "other_category")

    with pytest.raises(ApiError) as raised:
        update_claim(case_id, payload, owner, db, None)

    assert raised.value.code == UNSUPPORTED_CASE_TYPE
    assert raised.value.status == 422


def test_intake_check_is_idempotent_for_an_unchanged_revision(
    client: TestClient, seeded: None
) -> None:
    """Re-running the gate on an unchanged revision returns the cached result (B3)."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]

    first = client.post(
        f"/api/cases/{case_id}/intake-check", json={"expected_revision": 1}, headers=headers
    )
    second = client.post(
        f"/api/cases/{case_id}/intake-check", json={"expected_revision": 1}, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json() == {"status": "ready", "questions": []}


def test_case_list_and_detail_are_owner_scoped(client: TestClient, seeded: None) -> None:
    """Another preparer sees neither the case in their list nor by direct ID (B8, B9)."""
    owner_headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=owner_headers).json()["case_id"]

    listed = client.get("/api/cases").json()
    assert [row["case_id"] for row in listed["items"]] == [case_id]
    assert listed["next_cursor"] is None

    other_headers = auth_headers(client, email=SECOND_PREPARER_EMAIL)
    assert client.get("/api/cases").json()["items"] == []
    assert client.get(f"/api/cases/{case_id}").status_code == 404
    assert client.patch(
        f"/api/cases/{case_id}/claim",
        json={"expected_revision": 1, "claim": READY_CLAIM},
        headers=other_headers,
    ).status_code == 404


def test_case_detail_shape_matches_the_contract(client: TestClient, seeded: None) -> None:
    """``GET /cases/{id}`` returns the composite object the UI expects (B9)."""
    headers = auth_headers(client)
    case_id = client.post("/api/cases", json=READY_CLAIM, headers=headers).json()["case_id"]

    body = client.get(f"/api/cases/{case_id}").json()

    assert set(body) == {
        "case_id",
        "revision",
        "claim",
        "intake",
        "documents",
        "latest_job",
        "latest_analysis",
        "readiness",
        "submissions",
        "activity",
        "responses",
    }
    assert body["documents"] == []
    assert body["latest_job"] is None
    assert body["latest_analysis"] is None
    assert body["submissions"] == []
    assert body["responses"] == []
    # Activity is derived from durable rows, so case creation is already there.
    assert [entry["type"] for entry in body["activity"]] == ["claim_created"]
    assert set(body["claim"]["dates"]) == {"contract", "delivery", "invoice", "payment_due"}


def test_unknown_date_stays_null(client: TestClient, seeded: None) -> None:
    """An unknown date is stored as explicit null, never fabricated (B3)."""
    headers = auth_headers(client)
    dates = {"contract": None, "delivery": None, "invoice": "2026-06-10", "payment_due": None}

    case_id = client.post(
        "/api/cases", json=claim_with(dates=dates), headers=headers
    ).json()["case_id"]

    stored = client.get(f"/api/cases/{case_id}").json()["claim"]["dates"]
    assert stored == dates


def test_mutations_require_a_csrf_token(client: TestClient, seeded: None) -> None:
    """A session cookie alone is not enough to mutate state (B8)."""
    auth_headers(client)  # establishes the session cookie on the client

    response = client.post("/api/cases", json=READY_CLAIM)

    assert response.status_code == 403
