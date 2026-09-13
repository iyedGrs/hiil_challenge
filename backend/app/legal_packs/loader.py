"""Idempotent legal-pack loader (spec/backend.md B5).

Reads the versioned JSON asset(s) shipped in this package and upserts
``LegalPack``, ``LegalReference`` and ``Check`` rows. Matching is always by the
natural/composite key already defined on the models (``version`` /
``pack_version, reference_id`` / ``pack_version, check_id`` -- see
``app/models/legal.py``), never by a generated ID, so re-running the loader
updates existing rows in place and never creates duplicates. This mirrors the
upsert pattern in ``app/seed_demo.py``.

The model never selects legal provisions or checks (B1 refinement 2, B5): this
module is the *only* writer of ``Check.legal_reference_ids`` and
``LegalReference`` rows, and it only ever copies them from the committed JSON
asset below. Nothing in the request/response path can set these fields.

Every check in the shipped pack carries ``legal_reference_ids: []`` because no
Tunisian legal reference here has been reviewed by a practitioner. Should a
future pack add ``legal_references`` entries, this loader still refuses to
promote them past ``review_status="draft"``: only a human editing the asset's
``reviewer``/``reviewed_at``/``review_status`` fields (and, at the pack level,
``review_status``/``coverage``) can mark something reviewed. Unknown effective
dates stay ``null``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain.enums import CaseType, LegalCoverage, SubjectType
from app.models.legal import Check, LegalPack, LegalReference

logger = logging.getLogger("app.legal_packs.loader")

#: Every asset file loaded at startup / by the standalone script. Add new
#: pack files here as they are authored; each file's own ``version`` field
#: remains the natural key, so filenames are just a discovery convenience.
PACK_ASSET_FILENAMES: tuple[str, ...] = ("tn_goods_v1.json",)


@dataclass(frozen=True)
class LoadedPack:
    """Summary of one loaded pack, returned for logging/tests."""

    version: str
    case_type: CaseType
    coverage: LegalCoverage
    check_count: int
    legal_reference_count: int
    asset_sha256: str


def _read_asset_bytes(filename: str) -> bytes:
    """Return the raw bytes of a packaged JSON asset."""
    package_files = resources.files(__package__)
    return (package_files / filename).read_bytes()


def _parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO date string, keeping ``None`` unknown dates unknown (B5)."""
    if value is None:
        return None
    return date.fromisoformat(value)


def _upsert_legal_reference(
    db: DbSession, pack_version: str, payload: dict[str, Any]
) -> LegalReference:
    """Create or refresh one reference row, matched by ``(pack_version, reference_id)``.

    ``review_status`` defaults to ``draft`` and ``reviewer``/``reviewed_at`` default
    to ``None`` unless the asset itself carries a genuine recorded review -- this
    loader never invents a review (B5).
    """
    reference_id = payload["reference_id"]
    existing = db.get(LegalReference, (pack_version, reference_id))
    review_status = payload.get("review_status", "draft")
    reviewer = payload.get("reviewer")
    reviewed_at = _parse_iso_date(payload.get("reviewed_at"))
    if review_status != "draft" and (reviewer is None or reviewed_at is None):
        # A non-draft claim with no recorded reviewer/date is not a genuine review;
        # refuse to promote it rather than publish an unearned label (B5).
        raise ValueError(
            f"Legal reference {reference_id!r} claims review_status={review_status!r} "
            "without a reviewer and reviewed_at; this asset cannot assert a review "
            "that was not actually recorded."
        )

    fields = dict(
        code_article=payload["code_article"],
        original_text=payload["original_text"],
        language=payload["language"],
        source_url=payload.get("source_url"),
        source_page=payload.get("source_page"),
        effective_from=_parse_iso_date(payload.get("effective_from")),
        effective_to=_parse_iso_date(payload.get("effective_to")),
        conditions=payload.get("conditions", {}),
        exceptions=payload.get("exceptions", []),
        related_reference_ids=payload.get("related_reference_ids", []),
        review_status=review_status,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    reference = LegalReference(pack_version=pack_version, reference_id=reference_id, **fields)
    db.add(reference)
    db.flush()
    return reference


def _upsert_check(db: DbSession, pack_version: str, payload: dict[str, Any]) -> Check:
    """Create or refresh one check row, matched by ``(pack_version, check_id)``.

    ``legal_reference_ids`` is copied verbatim from the asset -- the model has no
    legal-reference output field and never reaches this code path (B5).
    """
    check_id = payload["check_id"]
    existing = db.get(Check, (pack_version, check_id))

    fields = dict(
        label=payload["label"],
        basis=payload["basis"],
        legal_reference_ids=list(payload.get("legal_reference_ids", [])),
        review_status=payload.get("review_status", "draft"),
        applies_when=payload.get("applies_when", {}),
        subject_type=SubjectType(payload["subject_type"]),
        satisfied_by=list(payload.get("satisfied_by", [])),
        actions=list(payload.get("actions", [])),
        sort_order=int(payload.get("sort_order", 0)),
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    check = Check(pack_version=pack_version, check_id=check_id, **fields)
    db.add(check)
    db.flush()
    return check


def load_pack_from_bytes(db: DbSession, raw: bytes, *, source_filename: str) -> LoadedPack:
    """Upsert one pack's rows from raw JSON bytes. Safe to call repeatedly.

    Args:
        db: Open session; the caller owns the transaction (mirrors
            ``app/seed_demo.py``).
        raw: Exact bytes of the JSON asset, hashed into ``LegalPack.asset_sha256``
            so a change to the shipped file is detectable.
        source_filename: Recorded only for the log line; the pack's own
            ``version`` field is the natural key, not the filename.
    """
    payload = json.loads(raw.decode("utf-8"))
    version = payload["version"]
    case_type = CaseType(payload["case_type"])
    coverage = LegalCoverage(payload.get("coverage", LegalCoverage.unvalidated.value))
    review_status = payload.get("review_status", "draft")

    if coverage is LegalCoverage.validated and review_status != "reviewed":
        # Refuse to advertise a validated pack that was not actually reviewed;
        # B5 forbids inventing a "lawyer-reviewed" label.
        raise ValueError(
            f"Pack {version!r} sets coverage=validated but review_status={review_status!r}; "
            "coverage may only be validated once a real review is recorded."
        )

    asset_sha256 = hashlib.sha256(raw).hexdigest()
    loaded_at = datetime.now(tz=timezone.utc)

    pack = db.get(LegalPack, version)
    if pack is None:
        pack = LegalPack(version=version, case_type=case_type)
        db.add(pack)

    pack.case_type = case_type
    pack.coverage = coverage
    pack.review_status = review_status
    pack.source_label = payload.get("source_label")
    pack.asset_sha256 = asset_sha256
    pack.loaded_at = loaded_at
    pack.labels = payload.get("labels", {})
    db.flush()

    reference_payloads = payload.get("legal_references", [])
    seen_reference_ids: set[str] = set()
    for reference_payload in reference_payloads:
        _upsert_legal_reference(db, version, reference_payload)
        seen_reference_ids.add(reference_payload["reference_id"])

    # Drop reference rows this asset no longer declares, so the pack version's
    # rows always mirror the committed asset exactly (still scoped to this one
    # pack_version; other packs are untouched).
    stale_references = db.scalars(
        select(LegalReference).where(
            LegalReference.pack_version == version,
            LegalReference.reference_id.not_in(seen_reference_ids),
        )
    ).all()
    for stale in stale_references:
        db.delete(stale)

    check_payloads = payload.get("checks", [])
    seen_check_ids: set[str] = set()
    for check_payload in check_payloads:
        _upsert_check(db, version, check_payload)
        seen_check_ids.add(check_payload["check_id"])

    stale_checks = db.scalars(
        select(Check).where(
            Check.pack_version == version,
            Check.check_id.not_in(seen_check_ids),
        )
    ).all()
    for stale in stale_checks:
        db.delete(stale)

    db.flush()

    logger.info(
        "Loaded legal pack version=%s case_type=%s coverage=%s checks=%d "
        "legal_references=%d source=%s sha256=%s",
        version,
        case_type.value,
        coverage.value,
        len(check_payloads),
        len(reference_payloads),
        source_filename,
        asset_sha256,
    )

    return LoadedPack(
        version=version,
        case_type=case_type,
        coverage=coverage,
        check_count=len(check_payloads),
        legal_reference_count=len(reference_payloads),
        asset_sha256=asset_sha256,
    )


def load_pack_file(db: DbSession, path: Path) -> LoadedPack:
    """Load one pack from an on-disk JSON file (used for ad-hoc/testing paths)."""
    return load_pack_from_bytes(db, path.read_bytes(), source_filename=path.name)


def load_all_packs(db: DbSession) -> list[LoadedPack]:
    """Load every packaged asset in ``PACK_ASSET_FILENAMES``. Safe to repeat."""
    return [
        load_pack_from_bytes(db, _read_asset_bytes(filename), source_filename=filename)
        for filename in PACK_ASSET_FILENAMES
    ]
