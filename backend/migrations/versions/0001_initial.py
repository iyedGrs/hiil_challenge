"""Initial schema for every persisted entity.

Revision ID: 0001_initial
Revises: None
Create Date: 2026-01-01

Spec reference: spec/backend.md B8 (persistence, jobs and permissions). This
migration is written by hand and covers the whole entity table in one step so
later slices extend the schema instead of competing over one initial migration.

Conventions (spec/backend.md B7):

* Money columns are ``NUMERIC(18, 3)``; never floating point.
* Timestamps are ``TIMESTAMPTZ`` and stored in UTC.
* Public opaque IDs are the primary keys, so routes address rows directly.
* Enumerated values are stored as short text, matching the VARCHAR-backed enums
  in :mod:`app.models`, so adding a value needs no type migration.
* ``ondelete`` is ``RESTRICT`` wherever a submitted snapshot, published run or
  preparer response could otherwise be destroyed (B10). Documents are detached
  via ``is_active``, never row-deleted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Width of the opaque public ID columns (prefix plus ten hex characters).
ID = sa.String(32)
#: Width of enum-backed text columns.
ENUM = sa.String(48)
#: Monetary type for TND: 12 integer digits and 3 fractional digits.
MONEY = sa.Numeric(18, 3)


def _json() -> postgresql.JSONB:
    """JSONB payload column type (PostgreSQL 16 target)."""
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    """Create every table in dependency order."""
    now = sa.text("now()")

    # --- Accounts, sessions and reviewer destinations (B8, B10) ---
    op.create_table(
        "users",
        sa.Column("id", ID, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("role", ENUM, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "sessions",
        sa.Column("id", ID, nullable=False),
        sa.Column("user_id", ID, nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "recipients",
        sa.Column("id", ID, nullable=False),
        sa.Column("reviewer_id", ID, nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("remit", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_recipients"),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name="fk_recipients_reviewer_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("reviewer_id", "label", name="uq_recipients_reviewer_id_label"),
    )
    op.create_index("ix_recipients_reviewer_id", "recipients", ["reviewer_id"])

    # --- Cases and claim revisions (B3, B7) ---
    op.create_table(
        "cases",
        sa.Column("id", ID, nullable=False),
        sa.Column("owner_id", ID, nullable=False),
        sa.Column("case_type", ENUM, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("intake_status", ENUM, nullable=False),
        sa.Column("reference_label", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cases"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_cases_owner_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_cases_owner_id", "cases", ["owner_id"])
    op.create_index("ix_cases_owner_id_updated_at", "cases", ["owner_id", "updated_at"])

    op.create_table(
        "claim_revisions",
        sa.Column("case_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("case_type", ENUM, nullable=False),
        sa.Column("claimant_name", sa.String(200), nullable=False),
        sa.Column("counterparty_name", sa.String(200), nullable=False),
        sa.Column("claimed_amount", MONEY, nullable=False),
        sa.Column("currency", ENUM, nullable=False),
        sa.Column("requested_outcome", ENUM, nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("date_contract", sa.Date(), nullable=True),
        sa.Column("date_delivery", sa.Date(), nullable=True),
        sa.Column("date_invoice", sa.Date(), nullable=True),
        sa.Column("date_payment_due", sa.Date(), nullable=True),
        sa.Column("follow_up_answers", _json(), nullable=False),
        sa.Column("claim_json", _json(), nullable=False),
        sa.Column("origin", ENUM, nullable=False),
        sa.Column("intake_status", ENUM, nullable=False),
        sa.Column("intake_questions", _json(), nullable=False),
        sa.Column("intake_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intake_gate_version", sa.String(64), nullable=True),
        sa.Column("created_by", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("case_id", "revision", name="pk_claim_revisions"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_claim_revisions_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_claim_revisions_created_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_claim_revisions_case_id", "claim_revisions", ["case_id"])

    # --- Documents, subjects and pages (B4, B6, B10) ---
    op.create_table(
        "documents",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("state", ENUM, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("detached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_code", sa.String(64), nullable=True),
        sa.Column("rejection_message", sa.String(500), nullable=True),
        sa.Column("extraction_version", sa.String(32), nullable=True),
        sa.Column("added_revision", sa.Integer(), nullable=False),
        sa.Column("detached_revision", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_documents_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_documents_uploaded_by_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        # Duplicate detection is scoped to the authorized case (B9).
        sa.UniqueConstraint("case_id", "sha256", name="uq_documents_case_id_sha256"),
    )
    op.create_index("ix_documents_case_id_is_active", "documents", ["case_id", "is_active"])

    op.create_table(
        "subjects",
        sa.Column("case_id", ID, nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("subject_type", ENUM, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("identifiers", _json(), nullable=False),
        sa.Column("linked_subject_id", sa.String(64), nullable=True),
        sa.Column("linkage_confirmed", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by_user", sa.Boolean(), nullable=False),
        sa.Column("source_document_id", ID, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("case_id", "subject_id", name="pk_subjects"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_subjects_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_subjects_source_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "case_id",
            "subject_type",
            "sequence",
            name="uq_subjects_case_id_subject_type_sequence",
        ),
    )
    op.create_index("ix_subjects_case_id_subject_type", "subjects", ["case_id", "subject_type"])

    op.create_table(
        "pages",
        sa.Column("id", ID, nullable=False),
        sa.Column("document_id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("method", ENUM, nullable=False),
        sa.Column("state", ENUM, nullable=False),
        sa.Column("quality", _json(), nullable=False),
        sa.Column("extraction_version", sa.String(32), nullable=False),
        sa.Column("image_key", sa.String(512), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pages"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_pages_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_pages_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_document_id_page_number"),
    )
    op.create_index("ix_pages_case_id", "pages", ["case_id"])
    op.create_index("ix_pages_document_id_state", "pages", ["document_id", "state"])

    # --- Extraction cache and candidate facts (B6, B7) ---
    op.create_table(
        "extractions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("document_id", ID, nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("extraction_version", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("execution_mode", ENUM, nullable=False),
        sa.Column("summary", _json(), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("rejected_fact_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_extractions"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_extractions_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_extractions_document_id_documents",
            ondelete="CASCADE",
        ),
        # Cache scope: case, document hash and every version input (B6).
        sa.UniqueConstraint(
            "case_id",
            "document_sha256",
            "extraction_version",
            "schema_version",
            "prompt_version",
            "model_version",
            name="uq_extractions_cache_key",
        ),
    )
    op.create_index("ix_extractions_document_id", "extractions", ["document_id"])

    op.create_table(
        "facts",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("extraction_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("currency_text", sa.String(32), nullable=True),
        sa.Column("normalized_value", MONEY, nullable=True),
        sa.Column("document_id", ID, nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("verification", ENUM, nullable=False),
        sa.Column("quarantine_reason", ENUM, nullable=True),
        sa.Column("extraction_version", sa.String(32), nullable=False),
        sa.Column("normalization_version", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_facts"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_facts_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
            name="fk_facts_extraction_id_extractions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_facts_document_id_documents",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_facts_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_facts_case_id_verification", "facts", ["case_id", "verification"])
    op.create_index("ix_facts_document_id_page", "facts", ["document_id", "page"])
    op.create_index("ix_facts_case_id_subject_id", "facts", ["case_id", "subject_id"])

    # --- Legal pack, references and checklist definitions (B5) ---
    op.create_table(
        "legal_packs",
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("case_type", ENUM, nullable=False),
        sa.Column("coverage", ENUM, nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("source_label", sa.String(500), nullable=True),
        sa.Column("asset_sha256", sa.String(64), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("version", name="pk_legal_packs"),
    )
    op.create_index("ix_legal_packs_case_type", "legal_packs", ["case_type"])

    op.create_table(
        "legal_references",
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=False),
        sa.Column("code_article", sa.String(200), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("source_page", sa.String(64), nullable=True),
        # Unknown effective dates stay unknown (B5).
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("conditions", _json(), nullable=False),
        sa.Column("exceptions", _json(), nullable=False),
        sa.Column("related_reference_ids", _json(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=True),
        sa.Column("reviewed_at", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("pack_version", "reference_id", name="pk_legal_references"),
        sa.ForeignKeyConstraint(
            ["pack_version"],
            ["legal_packs.version"],
            name="fk_legal_references_pack_version_legal_packs",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "checks",
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("check_id", sa.String(100), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("basis", sa.String(64), nullable=False),
        sa.Column("legal_reference_ids", _json(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("applies_when", _json(), nullable=False),
        sa.Column("subject_type", ENUM, nullable=False),
        sa.Column("satisfied_by", _json(), nullable=False),
        sa.Column("actions", _json(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("pack_version", "check_id", name="pk_checks"),
        sa.ForeignKeyConstraint(
            ["pack_version"],
            ["legal_packs.version"],
            name="fk_checks_pack_version_legal_packs",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_checks_pack_version_subject_type", "checks", ["pack_version", "subject_type"])

    # --- Published runs and validated results (B7) ---
    op.create_table(
        "analyses",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("execution_mode", ENUM, nullable=False),
        sa.Column("checklist_version", sa.String(64), nullable=False),
        sa.Column("legal_coverage", ENUM, nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("normalization_version", sa.String(32), nullable=True),
        sa.Column("input_snapshot", _json(), nullable=False),
        sa.Column("coverage", _json(), nullable=False),
        sa.Column("reconciliation", _json(), nullable=True),
        sa.Column("disclosures", _json(), nullable=False),
        sa.Column("reviewed_document_ids", _json(), nullable=False),
        sa.Column("job_id", ID, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_analyses_case_id_cases",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_analyses_case_id_created_at", "analyses", ["case_id", "created_at"])
    op.create_index("ix_analyses_case_id_revision", "analyses", ["case_id", "revision"])

    op.create_table(
        "findings",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("check_id", sa.String(100), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("last_result", ENUM, nullable=True),
        sa.Column("last_reason_code", ENUM, nullable=True),
        sa.Column("last_delta", ENUM, nullable=True),
        sa.Column("first_seen_analysis_id", ID, nullable=True),
        sa.Column("last_seen_analysis_id", ID, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_findings"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_findings_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_findings_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        # Stable finding identity (B7).
        sa.UniqueConstraint(
            "case_id",
            "check_id",
            "subject_id",
            name="uq_findings_case_id_check_id_subject_id",
        ),
    )
    op.create_index("ix_findings_case_id_status", "findings", ["case_id", "status"])

    op.create_table(
        "check_results",
        sa.Column("analysis_id", ID, nullable=False),
        sa.Column("check_id", sa.String(100), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("finding_id", ID, nullable=True),
        sa.Column("result", ENUM, nullable=False),
        sa.Column("reason_code", ENUM, nullable=False),
        sa.Column("finding_status", ENUM, nullable=True),
        sa.Column("delta", ENUM, nullable=True),
        sa.Column("basis", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("evidence_refs", _json(), nullable=False),
        sa.Column("fact_ids", _json(), nullable=False),
        sa.Column("reviewed_document_ids", _json(), nullable=False),
        sa.Column("legal_reference_ids", _json(), nullable=False),
        sa.Column("actions", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("analysis_id", "check_id", "subject_id", name="pk_check_results"),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name="fk_check_results_analysis_id_analyses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_check_results_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name="fk_check_results_finding_id_findings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "subject_id"],
            ["subjects.case_id", "subjects.subject_id"],
            name="fk_check_results_case_id_subject_id_subjects",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_check_results_case_id_check_id", "check_results", ["case_id", "check_id"])
    op.create_index("ix_check_results_finding_id", "check_results", ["finding_id"])

    op.create_table(
        "finding_responses",
        sa.Column("id", ID, nullable=False),
        sa.Column("finding_id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("analysis_id", ID, nullable=True),
        sa.Column("action", ENUM, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("document_ids", _json(), nullable=False),
        sa.Column("created_by", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_finding_responses"),
        # RESTRICT: preparer responses stay attached to the version they answered
        # and must survive later edits (B7, B10).
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name="fk_finding_responses_finding_id_findings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_finding_responses_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_finding_responses_created_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_finding_responses_finding_id", "finding_responses", ["finding_id"])
    op.create_index(
        "ix_finding_responses_case_id_revision", "finding_responses", ["case_id", "revision"]
    )

    # --- Exports, submissions and reviewer events (B10) ---
    op.create_table(
        "exports",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("analysis_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", ENUM, nullable=False),
        sa.Column("acknowledge_unresolved", sa.Boolean(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("manifest", _json(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_by", ID, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_exports"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_exports_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name="fk_exports_analysis_id_analyses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_exports_created_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_exports_case_id_created_at", "exports", ["case_id", "created_at"])
    op.create_index("ix_exports_analysis_id", "exports", ["analysis_id"])

    op.create_table(
        "submissions",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("analysis_id", ID, nullable=False),
        sa.Column("recipient_id", ID, nullable=False),
        sa.Column("reviewer_id", ID, nullable=False),
        sa.Column("preparer_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("checklist_version", sa.String(64), nullable=False),
        sa.Column("state", ENUM, nullable=False),
        sa.Column("acknowledge_unresolved", sa.Boolean(), nullable=False),
        sa.Column("manifest", _json(), nullable=False),
        sa.Column("claim_snapshot", _json(), nullable=False),
        sa.Column("response_snapshot", _json(), nullable=False),
        sa.Column("export_id", ID, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_submissions_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name="fk_submissions_analysis_id_analyses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["recipients.id"],
            name="fk_submissions_recipient_id_recipients",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name="fk_submissions_reviewer_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preparer_id"],
            ["users.id"],
            name="fk_submissions_preparer_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["export_id"],
            ["exports.id"],
            name="fk_submissions_export_id_exports",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_submissions_reviewer_id_submitted_at", "submissions", ["reviewer_id", "submitted_at"]
    )
    op.create_index(
        "ix_submissions_case_id_submitted_at", "submissions", ["case_id", "submitted_at"]
    )

    op.create_table(
        "submission_documents",
        sa.Column("submission_id", ID, nullable=False),
        sa.Column("document_id", ID, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("submission_id", "document_id", name="pk_submission_documents"),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_submission_documents_submission_id_submissions",
            ondelete="RESTRICT",
        ),
        # RESTRICT: detaching a file from the working case must not destroy a
        # submitted version (B10).
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_submission_documents_document_id_documents",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_submission_documents_document_id", "submission_documents", ["document_id"])

    op.create_table(
        "review_events",
        sa.Column("id", ID, nullable=False),
        sa.Column("submission_id", ID, nullable=False),
        sa.Column("event_type", ENUM, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("actor_id", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_review_events"),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_review_events_submission_id_submissions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_review_events_actor_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_review_events_submission_id_created_at", "review_events", ["submission_id", "created_at"]
    )

    # --- Durable jobs, usage and idempotency (B8) ---
    op.create_table(
        "jobs",
        sa.Column("id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("kind", ENUM, nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("phase", ENUM, nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("execution_mode", ENUM, nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("result_analysis_id", ID, nullable=True),
        sa.Column("result_export_id", ID, nullable=True),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("requested_by", ID, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_jobs_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_analysis_id"],
            ["analyses.id"],
            name="fk_jobs_result_analysis_id_analyses",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["result_export_id"],
            ["exports.id"],
            name="fk_jobs_result_export_id_exports",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_jobs_requested_by_users",
            ondelete="RESTRICT",
        ),
        # One durable job per revision/idempotency key (B8).
        sa.UniqueConstraint(
            "case_id",
            "kind",
            "idempotency_key",
            name="uq_jobs_case_id_kind_idempotency_key",
        ),
    )
    op.create_index("ix_jobs_status_available_at", "jobs", ["status", "available_at"])
    op.create_index("ix_jobs_case_id_kind_status", "jobs", ["case_id", "kind", "status"])
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])

    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", ID, nullable=False),
        sa.Column("case_id", ID, nullable=False),
        sa.Column("analysis_id", ID, nullable=True),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("execution_mode", ENUM, nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reserved_cost_usd", MONEY, nullable=False),
        sa.Column("actual_cost_usd", MONEY, nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("outcome_uncertain", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_usage_records_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_usage_records_case_id_cases",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_usage_records_job_id", "usage_records", ["job_id"])
    op.create_index("ix_usage_records_case_id_created_at", "usage_records", ["case_id", "created_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("case_id", ID, nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", ID, nullable=True),
        sa.Column("result_id", ID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("case_id", "scope", "key", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_idempotency_keys_case_id_cases",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_idempotency_keys_job_id_jobs",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_idempotency_keys_job_id", "idempotency_keys", ["job_id"])


def downgrade() -> None:
    """Drop every table in reverse dependency order."""
    op.drop_index("ix_idempotency_keys_job_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_usage_records_case_id_created_at", table_name="usage_records")
    op.drop_index("ix_usage_records_job_id", table_name="usage_records")
    op.drop_table("usage_records")

    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_case_id_kind_status", table_name="jobs")
    op.drop_index("ix_jobs_status_available_at", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_review_events_submission_id_created_at", table_name="review_events")
    op.drop_table("review_events")

    op.drop_index("ix_submission_documents_document_id", table_name="submission_documents")
    op.drop_table("submission_documents")

    op.drop_index("ix_submissions_case_id_submitted_at", table_name="submissions")
    op.drop_index("ix_submissions_reviewer_id_submitted_at", table_name="submissions")
    op.drop_table("submissions")

    op.drop_index("ix_exports_analysis_id", table_name="exports")
    op.drop_index("ix_exports_case_id_created_at", table_name="exports")
    op.drop_table("exports")

    op.drop_index("ix_finding_responses_case_id_revision", table_name="finding_responses")
    op.drop_index("ix_finding_responses_finding_id", table_name="finding_responses")
    op.drop_table("finding_responses")

    op.drop_index("ix_check_results_finding_id", table_name="check_results")
    op.drop_index("ix_check_results_case_id_check_id", table_name="check_results")
    op.drop_table("check_results")

    op.drop_index("ix_findings_case_id_status", table_name="findings")
    op.drop_table("findings")

    op.drop_index("ix_analyses_case_id_revision", table_name="analyses")
    op.drop_index("ix_analyses_case_id_created_at", table_name="analyses")
    op.drop_table("analyses")

    op.drop_index("ix_checks_pack_version_subject_type", table_name="checks")
    op.drop_table("checks")

    op.drop_table("legal_references")

    op.drop_index("ix_legal_packs_case_type", table_name="legal_packs")
    op.drop_table("legal_packs")

    op.drop_index("ix_facts_case_id_subject_id", table_name="facts")
    op.drop_index("ix_facts_document_id_page", table_name="facts")
    op.drop_index("ix_facts_case_id_verification", table_name="facts")
    op.drop_table("facts")

    op.drop_index("ix_extractions_document_id", table_name="extractions")
    op.drop_table("extractions")

    op.drop_index("ix_pages_document_id_state", table_name="pages")
    op.drop_index("ix_pages_case_id", table_name="pages")
    op.drop_table("pages")

    op.drop_index("ix_subjects_case_id_subject_type", table_name="subjects")
    op.drop_table("subjects")

    op.drop_index("ix_documents_case_id_is_active", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_claim_revisions_case_id", table_name="claim_revisions")
    op.drop_table("claim_revisions")

    op.drop_index("ix_cases_owner_id_updated_at", table_name="cases")
    op.drop_index("ix_cases_owner_id", table_name="cases")
    op.drop_table("cases")

    op.drop_index("ix_recipients_reviewer_id", table_name="recipients")
    op.drop_table("recipients")

    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
