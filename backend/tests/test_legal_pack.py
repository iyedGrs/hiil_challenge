"""Legal-pack loader and ``GET /config`` coverage checks (spec/backend.md B5, B9, B11).

Covers: the shipped pack loads without error, re-loading is idempotent (no
duplicate rows, in-place update), every check ships with
``legal_reference_ids == []`` since nothing here has been reviewed, and
``GET /config`` reflects ``legal_coverage=unvalidated`` through the real
loaded-pack lookup rather than a hardcoded literal.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import CaseType, LegalCoverage, SubjectType
from app.legal_packs.loader import load_all_packs, load_pack_from_bytes
from app.models.legal import Check, LegalPack, LegalReference


def test_load_all_packs_succeeds_and_matches_settings_version(db: Session) -> None:
    """The shipped pack loads without error under its documented version."""
    loaded = load_all_packs(db)
    db.commit()

    assert len(loaded) == 1
    summary = loaded[0]
    assert summary.version == "tn-goods-v1"
    assert summary.case_type == CaseType.unpaid_goods_invoice
    assert summary.coverage == LegalCoverage.unvalidated
    assert summary.check_count >= 5
    assert summary.asset_sha256  # non-empty hex digest

    pack = db.get(LegalPack, "tn-goods-v1")
    assert pack is not None
    assert pack.case_type == CaseType.unpaid_goods_invoice
    assert pack.coverage == LegalCoverage.unvalidated
    assert pack.review_status == "draft"
    assert pack.asset_sha256 == summary.asset_sha256
    assert pack.loaded_at is not None
    assert pack.source_label  # a non-empty honest provenance string


def test_loading_twice_is_idempotent(db: Session) -> None:
    """Re-running the loader updates rows in place and never duplicates them."""
    load_all_packs(db)
    db.commit()

    before_packs = db.scalar(select(func.count()).select_from(LegalPack))
    before_checks = db.scalar(select(func.count()).select_from(Check))
    before_references = db.scalar(select(func.count()).select_from(LegalReference))

    load_all_packs(db)
    db.commit()

    assert db.scalar(select(func.count()).select_from(LegalPack)) == before_packs
    assert db.scalar(select(func.count()).select_from(Check)) == before_checks
    assert db.scalar(select(func.count()).select_from(LegalReference)) == before_references
    assert before_packs == 1
    assert before_checks >= 5


def test_all_checks_have_no_legal_reference_ids(db: Session) -> None:
    """Every shipped check carries ``legal_reference_ids == []`` (B5).

    No Tunisian legal reference in this pack has been reviewed by a
    practitioner, so nothing may claim a fixed statutory citation.
    """
    load_all_packs(db)
    db.commit()

    checks = db.scalars(select(Check).where(Check.pack_version == "tn-goods-v1")).all()
    assert len(checks) >= 5
    for check in checks:
        assert check.legal_reference_ids == []
        assert check.review_status == "draft"
        assert check.applies_when == {"case_type": "unpaid_goods_invoice"}
        # ``reconciliation`` marks a check that Decimal code decides on its own;
        # it is never handed to the model (spec/backend.md B7).
        assert check.basis in {"checklist", "evidence_guidance", "reconciliation"}

    # No legal references were shipped either: the safer, spec-preferred choice
    # when no reviewed reference exists (B5).
    references = db.scalars(
        select(LegalReference).where(LegalReference.pack_version == "tn-goods-v1")
    ).all()
    assert references == []


def test_delivery_evidence_check_matches_the_b5_example(db: Session) -> None:
    """``delivery_evidence`` matches the exact example given in spec/backend.md B5."""
    load_all_packs(db)
    db.commit()

    check = db.get(Check, ("tn-goods-v1", "delivery_evidence"))
    assert check is not None
    assert check.label == "Evidence supporting receipt of goods"
    assert check.basis == "evidence_guidance"
    assert check.legal_reference_ids == []
    assert check.subject_type == SubjectType.invoice
    satisfied_types = {entry["type"] for entry in check.satisfied_by}
    assert satisfied_types == {"delivery_acknowledgment", "receipt_confirmation_correspondence"}
    for entry in check.satisfied_by:
        assert entry["required_links"] == ["parties", "transaction"]


def test_referenced_attachment_present_check_targets_annex_subjects(db: Session) -> None:
    """The annex template check exists for other agents' code to instantiate (B6)."""
    load_all_packs(db)
    db.commit()

    check = db.get(Check, ("tn-goods-v1", "referenced_attachment_present"))
    assert check is not None
    assert check.subject_type == SubjectType.referenced_annex
    assert check.basis == "checklist"
    assert check.legal_reference_ids == []
    assert check.satisfied_by  # at least one acceptable-evidence condition


def test_loader_rejects_an_unearned_validated_claim(db: Session) -> None:
    """A pack cannot claim ``coverage=validated`` without a recorded review (B5)."""
    payload = {
        "version": "tn-fake-v1",
        "case_type": "unpaid_goods_invoice",
        "review_status": "draft",
        "coverage": "validated",
        "source_label": "test",
        "checks": [],
    }
    raw = json.dumps(payload).encode("utf-8")

    with pytest.raises(ValueError):
        load_pack_from_bytes(db, raw, source_filename="tn-fake-v1.json")
    db.rollback()


def test_config_reports_unvalidated_legal_coverage_through_the_loaded_pack(
    client: TestClient, db: Session
) -> None:
    """``GET /config`` reflects the real loaded-pack coverage, end to end (B5, B9)."""
    load_all_packs(db)
    db.commit()

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["legal_coverage"] == {
        CaseType.unpaid_goods_invoice.value: LegalCoverage.unvalidated.value
    }

    # The pack row backing this answer is real, not a mock.
    pack = db.get(LegalPack, "tn-goods-v1")
    assert pack is not None
    assert pack.coverage == LegalCoverage.unvalidated


def test_config_falls_back_to_unvalidated_when_no_pack_is_loaded(client: TestClient) -> None:
    """With an empty ``legal_packs`` table, ``/config`` still answers safely (B5).

    Every supported case type is still present in the map: a missing pack means
    ``unvalidated``, never an absent key the client has to interpret.
    """
    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["legal_coverage"] == {
        CaseType.unpaid_goods_invoice.value: LegalCoverage.unvalidated.value
    }
