"""Reviewer package builder (spec/backend.md B10).

Produces one ZIP containing the deterministic claim document, the evidence
bordereau, the verification summary and the original pieces, exactly:

    01_requete_introductive_instance.pdf
    02_bordereau_des_pieces.pdf
    03_resume_verification.pdf
    pieces/P01_<sanitized original filename>
    pieces/P02_...

Everything is rendered from backend templates and stored validated data. There
is **no extra AI drafting call** (B10): a package is an assembly of what was
already validated, not a new piece of generated prose. Nothing is invented: a
value the system has no field for is rendered as ``À compléter`` and a
value that was looked for but not found is rendered as ``Non renseigné``
(:mod:`app.pipeline.export_pdf`).

Three labelling rules the templates enforce, because a reviewer must be able to
tell these apart (B10):

* the preparer's **claim** is an allegation,
* a **documentary fact** is text quoted from an uploaded file,
* a preparer **explanation** is the preparer's own statement.

``export.manifest`` keeps an internal JSON record of what was packaged (spec:
"Keep export.manifest stored in the DB ... JSON is only excluded from the
ZIP"), so the disclosures and evidence index survive even though no ``.json``
file ships inside the archive itself.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ai.contracts import FactKind
from app.domain.enums import (
    AnalysisStatus,
    CaseType,
    ExportState,
    FactVerification,
    FindingStatus,
    LegalCoverage,
    RequestedOutcome,
)
from app.errors import UNSUPPORTED_CASE_TYPE, ApiError
from app.files import read_bytes, sha256_hex, write_bytes
from app.models.analysis import Analysis, CheckResultRow
from app.models.base import utcnow
from app.models.case import Case, ClaimRevision
from app.models.document import Document
from app.models.fact import Extraction, Fact
from app.models.finding import Finding, FindingResponse
from app.models.job import Job
from app.models.legal import Check
from app.models.subject import Subject
from app.models.submission import Export
from app.pipeline.export_pdf import (
    NON_RENSEIGNE,
    BordereauPdfData,
    BordereauRow,
    CheckRowData,
    ClaimPdfData,
    SummaryPdfData,
    render_bordereau_pdf,
    render_claim_pdf,
    render_summary_pdf,
)
from app.pipeline.readiness import case_readiness

logger = logging.getLogger("app.pipeline.export")

#: Storage key template for a finished package.
EXPORT_KEY = "exports/{case_id}/{export_id}.zip"

#: Fixed disclaimer, French with accents (spec export). Deliberately blunt: the
#: package must not read as a legal opinion, a certification or a court filing
#: (B1, B10).
DISCLAIMER_LINES: tuple[str, ...] = (
    "Ce dossier est une préparation de documents. Il ne constitue ni un avis "
    "juridique, ni une certification, ni un dépôt devant une juridiction.",
    "Les vérifications portent sur la présence, la lisibilité et la cohérence "
    "interne des pièces fournies. Elles n'authentifient aucun document, ne "
    "déterminent aucune responsabilité et n'évaluent aucun préjudice.",
)

_REQUESTED_OUTCOME_LABELS: dict[RequestedOutcome, str] = {
    RequestedOutcome.payment: "Paiement",
    RequestedOutcome.payment_plan: "Échéancier de paiement",
}

#: Closed document-type vocabulary (app.ai.contracts.DocumentTypeLabel) mapped
#: to French. A value outside this map (only "other" today) falls back to the
#: raw stored value, escaped at render time.
_DOCUMENT_TYPE_LABELS_FR: dict[str, str] = {
    "purchase_order": "Bon de commande",
    "invoice": "Facture",
    "delivery_note": "Bon de livraison",
    "payment_receipt": "Justificatif de paiement",
    "bank_statement": "Relevé bancaire",
    "credit_note": "Note de crédit",
    "contract": "Contrat",
    "correspondence": "Correspondance",
}

#: Which verified fact kind, if any, supplies the "Référence" column for a
#: given document type. A credit note has no reference fact kind of its own
#: (only ``credit_note_amount``), so it is deliberately absent here and falls
#: through to NON_RENSEIGNE.
_REFERENCE_FACT_KIND_BY_DOCTYPE: dict[str, str] = {
    "invoice": FactKind.invoice_number.value,
    "purchase_order": FactKind.order_reference.value,
    "contract": FactKind.contract_reference.value,
    "payment_receipt": FactKind.payment_reference.value,
    "bank_statement": FactKind.payment_reference.value,
}

#: Which verified fact kind, if any, supplies the "Date" column for a given
#: document type.
_DATE_FACT_KIND_BY_DOCTYPE: dict[str, str] = {
    "invoice": FactKind.invoice_date.value,
    "delivery_note": FactKind.delivery_date.value,
    "payment_receipt": FactKind.payment_date.value,
    "bank_statement": FactKind.payment_date.value,
}

_DATE_PREFIX_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})")
_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_REPEATED_UNDERSCORES = re.compile(r"_{2,}")
_REPEATED_DOTS = re.compile(r"\.{2,}")
_MAX_PIECE_FILENAME_LENGTH = 120

_UNSAFE_CASE_REFERENCE_CHARS = re.compile(r"[^A-Za-z0-9_-]")


# --- Pure helpers (no DB access; directly unit-testable) --------------------


def document_type_label(raw: str | None) -> str:
    """Map a stored ``Extraction.document_type`` value to its French label."""
    if raw is None:
        return NON_RENSEIGNE
    return _DOCUMENT_TYPE_LABELS_FR.get(raw, raw)


def reference_fact_kind_for_document_type(document_type: str | None) -> str | None:
    """Return the fact kind that may supply a reference for ``document_type``."""
    if document_type is None:
        return None
    return _REFERENCE_FACT_KIND_BY_DOCTYPE.get(document_type)


def date_fact_kind_for_document_type(document_type: str | None) -> str | None:
    """Return the fact kind that may supply a date for ``document_type``."""
    if document_type is None:
        return None
    return _DATE_FACT_KIND_BY_DOCTYPE.get(document_type)


def select_fact_value(facts: list[Fact], *, document_id: str, kind: str | None) -> str | None:
    """Return the first verified ``kind`` fact's value on ``document_id``, else None.

    "First" means lowest ``(page, created_at, id)`` -- never a fact borrowed
    from a kind the caller did not ask for.
    """
    if kind is None:
        return None
    candidates = [fact for fact in facts if fact.document_id == document_id and fact.kind == kind]
    if not candidates:
        return None
    candidates.sort(key=lambda fact: (fact.page, fact.created_at, fact.id))
    return candidates[0].value_text


def first_verified_value_across_pieces(
    facts: list[Fact], *, kind: str, ordered_document_ids: list[str]
) -> str | None:
    """Return the first ``kind`` fact's value across ``ordered_document_ids``, in order."""
    for document_id in ordered_document_ids:
        value = select_fact_value(facts, document_id=document_id, kind=kind)
        if value is not None:
            return value
    return None


def parse_leading_date(text: str) -> date | None:
    """Parse a strict leading ``dd/mm/YYYY`` prefix, or ``None`` if absent/invalid.

    Used only to sort copied source-text dates; the text itself is always
    displayed as-is (spec export).
    """
    text = text.strip()
    match = _DATE_PREFIX_RE.match(text)
    iso = _ISO_DATE_PREFIX_RE.match(text)
    if match:
        day, month, year = (int(group) for group in match.groups())
    elif iso:
        year, month, day = (int(group) for group in iso.groups())
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def sanitize_piece_filename(raw: str) -> str:
    """Sanitize a client-supplied filename for use as a ZIP entry name (B10).

    Basename only, NFKD-folded to ASCII, restricted to ``[A-Za-z0-9._-]``, no
    ``..`` segment, capped length preserving the extension.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _REPEATED_DOTS.sub("_", name)
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    name = _REPEATED_UNDERSCORES.sub("_", name)
    name = name.lstrip("._")
    if not name:
        return "document"
    if len(name) > _MAX_PIECE_FILENAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) <= 10:
            keep = _MAX_PIECE_FILENAME_LENGTH - len(ext) - 1
            name = f"{stem[:keep]}.{ext}" if keep > 0 else name[:_MAX_PIECE_FILENAME_LENGTH]
        else:
            name = name[:_MAX_PIECE_FILENAME_LENGTH]
    name = name.lstrip("._") or "document"
    assert ".." not in name and "/" not in name and "\\" not in name
    return name


def sanitize_case_reference(raw: str) -> str:
    """Sanitize a case reference for use in a download filename (spec export)."""
    return _UNSAFE_CASE_REFERENCE_CHARS.sub("_", raw or "") or "dossier"


def numbered_pieces(documents: list[Document]) -> list[tuple[Document, int, str, str]]:
    """Number ``documents`` in order and return ``(document, no, safe_name, zip_path)``.

    This numbering is computed once and shared by the bordereau, the claim's
    "Moyens de preuve" and the ZIP entry names (spec export).
    """
    result: list[tuple[Document, int, str, str]] = []
    for index, document in enumerate(documents, start=1):
        safe_name = sanitize_piece_filename(document.display_name)
        zip_path = f"pieces/P{index:02d}_{safe_name}"
        assert ".." not in zip_path
        result.append((document, index, safe_name, zip_path))
    return result


def _build_chronology(
    *,
    claim: ClaimRevision,
    verified_facts: list[Fact],
    piece_number_by_document_id: dict[str, int],
) -> list[tuple[str, str, str]]:
    """Build the claim PDF's chronology rows: sorted, deduplicated, French-labelled."""
    entries: list[tuple[date | None, str, str, str]] = []
    for value, event in (
        (claim.date_contract, "Date du contrat / bon de commande"),
        (claim.date_delivery, "Livraison"),
        (claim.date_invoice, "Facture"),
        (claim.date_payment_due, "Échéance de paiement"),
    ):
        if value is None:
            continue
        entries.append((value, value.strftime("%d/%m/%Y"), event, "Déclaration du demandeur"))

    for fact in verified_facts:
        if fact.kind != FactKind.payment_date.value:
            continue
        display = fact.value_text or ""
        piece_no = piece_number_by_document_id.get(fact.document_id)
        source = f"Pièce P{piece_no:02d}" if piece_no is not None else NON_RENSEIGNE
        # Not "partiel": whether a payment is partial is not a stored fact.
        entries.append((parse_leading_date(display), display, "Paiement documenté", source))

    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[date | None, str, str, str]] = []
    for sort_key, display, event, source in entries:
        dedupe_key = (display, event)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append((sort_key, display, event, source))

    deduped.sort(key=lambda entry: (entry[0] is None, entry[0] or date.min))
    return [(display, event, source) for _, display, event, source in deduped]


# --- Data gathering + rendering (DB-facing) ----------------------------------


def _verdict(db: DbSession, case: Case, analysis: Analysis) -> tuple[str, list[str]]:
    """Render the automatic readiness verdict (spec/progress.md change log)."""
    readiness = case_readiness(db, case_revision=case.revision, analysis=analysis)
    if readiness.status.value == "complete":
        return "Verdict du dossier : Dossier complet et cohérent - prêt à transmettre.", []
    if readiness.status.value == "needs_analysis":
        return "Verdict du dossier : Analyse requise.", readiness.reasons
    return "Verdict du dossier : Dossier incomplet.", readiness.reasons


def _summary_data(
    *,
    db: DbSession,
    case: Case,
    claim: ClaimRevision,
    analysis: Analysis,
    rows: list[CheckResultRow],
    subjects: dict[str, Subject],
    definitions: dict[str, Check],
    responses: list[tuple[Finding, FindingResponse]],
    pieces: list[tuple[Document, int, str, str]],
) -> SummaryPdfData:
    verdict_line, verdict_reasons = _verdict(db, case, analysis)

    scope_lines = [
        f"Analyse : {analysis.id}",
        f"Révision du dossier : {analysis.revision}",
        f"Statut de l'analyse : {analysis.status.value}",
        f"Mode d'exécution : {analysis.execution_mode.value}",
        f"Version du référentiel : {analysis.checklist_version}",
        f"Couverture juridique : {analysis.legal_coverage.value}",
    ]
    if analysis.legal_coverage is LegalCoverage.unvalidated:
        scope_lines.append(
            "Aucun référentiel juridique validé n'est disponible. Les vérifications "
            "ci-dessous sont des contrôles documentaires, pas des exigences légales certifiées."
        )
    coverage = analysis.coverage or {}
    scope_lines.append(
        f"Pages examinées : {coverage.get('reviewed_pages', 0)} - "
        f"pages illisibles : {coverage.get('unreadable_pages', 0)} - "
        f"éléments écartés : {coverage.get('rejected_facts', 0)}"
    )
    partial_warning = None
    if analysis.status is AnalysisStatus.partial:
        partial_warning = (
            "Analyse partielle : une partie des pièces n'a pas pu être examinée. "
            "L'absence d'un élément ci-dessous n'est donc pas concluante."
        )

    claim_lines = [
        f"Demandeur : {claim.claimant_name}",
        f"Partie adverse : {claim.counterparty_name}",
        f"Montant réclamé : {claim.claimed_amount} {claim.currency.value}",
        f"Résultat demandé : {claim.requested_outcome.value}",
        "Dates déclarées - contrat : {} / livraison : {} / facture : {} / échéance : {}".format(
            claim.date_contract or "inconnue",
            claim.date_delivery or "inconnue",
            claim.date_invoice or "inconnue",
            claim.date_payment_due or "inconnue",
        ),
    ]

    reconciliation_lines: list[str] | None = None
    if analysis.reconciliation:
        payload = analysis.reconciliation
        reconciliation_lines = [
            f"Solde d'après les documents déposés : {payload['documented_balance']} "
            f"{payload['currency']}",
            str(payload.get("coverage_note", "")),
        ]

    checks: list[CheckRowData] = []
    for row in rows:
        subject = subjects.get(row.subject_id)
        definition = definitions.get(row.check_id)
        label = definition.label if definition else row.check_id
        evidence_lines = [
            f"Fait documentaire - {ref['document_id']} p.{ref['page']} : "
            f"\"{str(ref['source_text'])[:200]}\""
            for ref in row.evidence_refs
        ]
        checks.append(
            CheckRowData(
                header=f"[{row.result.value}] {label}",
                subject_line=f"Objet : {subject.label if subject else row.subject_id}",
                reason_line=f"Motif : {row.reason_code.value}",
                message=row.message,
                status_line=(f"État : {row.finding_status.value}" if row.finding_status else None),
                evidence_lines=evidence_lines,
            )
        )

    unresolved_lines = [
        f"- {(definitions[row.check_id].label if row.check_id in definitions else row.check_id)}: {row.message}"
        for row in rows
        if row.finding_status is FindingStatus.open
    ]

    response_lines = [
        (
            f"- {finding.check_id} / {finding.subject_id}: {response.action.value}",
            response.explanation,
        )
        for finding, response in responses
    ]

    evidence_index = [
        (
            no,
            f"{safe_name} ({document.page_count or 0} page(s), {document.byte_size} octets)",
        )
        for document, no, safe_name, _zip_path in pieces
    ]

    return SummaryPdfData(
        case_reference=case.id,
        generated_at=utcnow().strftime("%d/%m/%Y"),
        verdict_line=verdict_line,
        verdict_reasons=verdict_reasons,
        disclaimer_lines=list(DISCLAIMER_LINES),
        scope_lines=scope_lines,
        partial_warning=partial_warning,
        claim_lines=claim_lines,
        narrative=claim.narrative,
        reconciliation_lines=reconciliation_lines,
        checks=checks,
        unresolved_lines=unresolved_lines,
        response_lines=response_lines,
        evidence_index=evidence_index,
    )


def _claim_data(
    *,
    case: Case,
    claim: ClaimRevision,
    analysis: Analysis,
    verified_facts: list[Fact],
    pieces: list[tuple[Document, int, str, str]],
    latest_document_type: dict[str, str | None],
) -> ClaimPdfData:
    ordered_document_ids = [document.id for document, _no, _safe, _zip in pieces]
    invoice_reference = (
        first_verified_value_across_pieces(
            verified_facts,
            kind=FactKind.invoice_number.value,
            ordered_document_ids=ordered_document_ids,
        )
        or NON_RENSEIGNE
    )
    piece_number_by_document_id = {document.id: no for document, no, _safe, _zip in pieces}
    chronology = _build_chronology(
        claim=claim,
        verified_facts=verified_facts,
        piece_number_by_document_id=piece_number_by_document_id,
    )
    evidence = [
        (no, document_type_label(latest_document_type.get(document.id)), zip_path.split("pieces/", 1)[1])
        for document, no, _safe, zip_path in pieces
    ]

    reconciliation = analysis.reconciliation
    documented_balance_display = NON_RENSEIGNE
    reconciliation_currency = claim.currency.value
    coverage_note: str | None = None
    balance_mismatch_note: str | None = None
    if reconciliation:
        documented_balance_display = str(reconciliation.get("documented_balance", NON_RENSEIGNE))
        reconciliation_currency = str(reconciliation.get("currency", claim.currency.value))
        coverage_note = str(reconciliation.get("coverage_note", ""))
        try:
            if Decimal(str(reconciliation["documented_balance"])) != claim.claimed_amount:
                balance_mismatch_note = "Le montant réclamé diffère du solde documenté."
        except (InvalidOperation, KeyError):
            pass

    return ClaimPdfData(
        case_reference=case.id,
        generated_at=utcnow().strftime("%d/%m/%Y"),
        claimant_name=claim.claimant_name,
        counterparty_name=claim.counterparty_name,
        invoice_reference=invoice_reference,
        claimed_amount=str(claim.claimed_amount),
        currency=claim.currency.value,
        requested_outcome_label=_REQUESTED_OUTCOME_LABELS[claim.requested_outcome],
        narrative=claim.narrative,
        chronology=chronology,
        evidence=evidence,
        documented_balance_display=documented_balance_display,
        reconciliation_currency=reconciliation_currency,
        coverage_note=coverage_note,
        balance_mismatch_note=balance_mismatch_note,
    )


def _bordereau_data(
    *,
    case: Case,
    claim: ClaimRevision,
    verified_facts: list[Fact],
    pieces: list[tuple[Document, int, str, str]],
    latest_document_type: dict[str, str | None],
) -> BordereauPdfData:
    rows: list[BordereauRow] = []
    for document, no, _safe, zip_path in pieces:
        doc_type_raw = latest_document_type.get(document.id)
        reference = (
            select_fact_value(
                verified_facts,
                document_id=document.id,
                kind=reference_fact_kind_for_document_type(doc_type_raw),
            )
            or NON_RENSEIGNE
        )
        date_display = (
            select_fact_value(
                verified_facts,
                document_id=document.id,
                kind=date_fact_kind_for_document_type(doc_type_raw),
            )
            or NON_RENSEIGNE
        )
        rows.append(
            BordereauRow(
                piece_no=no,
                type_label=document_type_label(doc_type_raw),
                reference=reference,
                date_display=date_display,
                filename=zip_path.split("pieces/", 1)[1],
                pages=str(document.page_count) if document.page_count else NON_RENSEIGNE,
            )
        )
    return BordereauPdfData(
        case_reference=case.id,
        generated_at=utcnow().strftime("%d/%m/%Y"),
        claimant_name=claim.claimant_name,
        counterparty_name=claim.counterparty_name,
        rows=rows,
    )


def build_export(db: DbSession, export: Export) -> None:
    """Assemble the ZIP for ``export`` and mark it ready (spec/backend.md B10).

    Raises:
        ApiError: when the analysis or case backing the export has gone
            missing, when the case type is unsupported, or when an original
            file cannot be read -- a package is never partially written.
    """
    from app.config import get_settings

    settings = get_settings()
    case = db.get(Case, export.case_id)
    analysis = db.get(Analysis, export.analysis_id)
    if case is None or analysis is None:  # pragma: no cover - FKs guarantee both
        raise ApiError("INTERNAL_ERROR", "The case or analysis for this export is missing.")

    if case.case_type is not CaseType.unpaid_goods_invoice:
        raise ApiError(UNSUPPORTED_CASE_TYPE, "This case type is not supported for export.")

    claim = db.get(ClaimRevision, (case.id, analysis.revision)) or db.scalar(
        select(ClaimRevision)
        .where(ClaimRevision.case_id == case.id)
        .order_by(ClaimRevision.revision.desc())
        .limit(1)
    )
    if claim is None:  # pragma: no cover
        raise ApiError("INTERNAL_ERROR", "The claim revision for this export is missing.")

    rows = list(
        db.scalars(select(CheckResultRow).where(CheckResultRow.analysis_id == analysis.id)).all()
    )
    subjects = {
        subject.subject_id: subject
        for subject in db.scalars(select(Subject).where(Subject.case_id == case.id)).all()
    }
    definitions = {
        check.check_id: check
        for check in db.scalars(
            select(Check).where(Check.pack_version == analysis.checklist_version)
        ).all()
    }
    responses = list(
        db.execute(
            select(Finding, FindingResponse)
            .join(FindingResponse, FindingResponse.finding_id == Finding.id)
            .where(Finding.case_id == case.id)
            .order_by(FindingResponse.created_at)
        ).all()
    )

    # Pieces = the documents currently uploaded on the case, in upload order.
    # Numbered exactly once and shared by every renderer and the ZIP names.
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case.id, Document.is_active.is_(True))
            .order_by(Document.created_at, Document.id)
        ).all()
    )
    pieces = numbered_pieces(documents)
    piece_ids = [document.id for document, _no, _safe, _zip in pieces]

    # Read every original upfront: never produce an incomplete package.
    piece_bytes: dict[str, bytes] = {}
    for document, _no, _safe, _zip in pieces:
        try:
            piece_bytes[document.id] = read_bytes(settings.file_storage_root, document.storage_key)
        except OSError as exc:
            raise ApiError(
                "INTERNAL_ERROR", "An original file for this case could not be read."
            ) from exc

    verified_facts = (
        list(
            db.scalars(
                select(Fact).where(
                    Fact.case_id == case.id,
                    Fact.verification == FactVerification.verified,
                    Fact.document_id.in_(piece_ids),
                )
            ).all()
        )
        if piece_ids
        else []
    )
    latest_document_type: dict[str, str | None] = {}
    if piece_ids:
        extractions = list(
            db.scalars(select(Extraction).where(Extraction.document_id.in_(piece_ids))).all()
        )
        for extraction in sorted(extractions, key=lambda e: e.created_at):
            latest_document_type[extraction.document_id] = extraction.document_type

    claim_pdf = render_claim_pdf(
        _claim_data(
            case=case,
            claim=claim,
            analysis=analysis,
            verified_facts=verified_facts,
            pieces=pieces,
            latest_document_type=latest_document_type,
        )
    )
    bordereau_pdf = render_bordereau_pdf(
        _bordereau_data(
            case=case,
            claim=claim,
            verified_facts=verified_facts,
            pieces=pieces,
            latest_document_type=latest_document_type,
        )
    )
    summary_pdf = render_summary_pdf(
        _summary_data(
            db=db,
            case=case,
            claim=claim,
            analysis=analysis,
            rows=rows,
            subjects=subjects,
            definitions=definitions,
            responses=responses,
            pieces=pieces,
        )
    )

    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "case_id": case.id,
        "export_id": export.id,
        "analysis_id": analysis.id,
        "revision": analysis.revision,
        "analysis_status": analysis.status.value,
        "execution_mode": analysis.execution_mode.value,
        "checklist_version": analysis.checklist_version,
        "legal_coverage": analysis.legal_coverage.value,
        "coverage": analysis.coverage,
        "disclosures": analysis.disclosures,
        "acknowledge_unresolved": export.acknowledge_unresolved,
        "unresolved_count": sum(1 for row in rows if row.finding_status is FindingStatus.open),
        "pieces": [
            {"piece_no": no, "document_id": document.id, "zip_path": zip_path}
            for document, no, _safe, zip_path in pieces
        ],
        "claim_is_an_allegation": True,
        "notice": (
            "Document preparation only. No legal advice, certification, "
            "authentication or court filing is implied."
        ),
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("01_requete_introductive_instance.pdf", claim_pdf)
        archive.writestr("02_bordereau_des_pieces.pdf", bordereau_pdf)
        archive.writestr("03_resume_verification.pdf", summary_pdf)
        for document, _no, _safe, zip_path in pieces:
            archive.writestr(zip_path, piece_bytes[document.id])

    payload = buffer.getvalue()
    storage_key = EXPORT_KEY.format(case_id=case.id, export_id=export.id)
    write_bytes(settings.file_storage_root, storage_key, payload)

    export.storage_key = storage_key
    export.byte_size = len(payload)
    export.sha256 = sha256_hex(payload)
    export.manifest = manifest
    export.state = ExportState.ready
    export.completed_at = utcnow()
    db.flush()
    logger.info("Export ready: export=%s bytes=%d", export.id, len(payload))


def handle_export_job(db: DbSession, job: Job) -> None:
    """Worker handler for ``JobKind.export`` (spec/backend.md B8, B10).

    A failure marks the export ``failed`` with a sanitized reason and re-raises, so
    the job records the failure too. ``GET /exports/{id}/content`` then answers
    409 rather than serving a half-written archive.
    """
    from app.domain.enums import JobPhase

    export_id = str(job.payload.get("export_id", ""))
    export = db.get(Export, export_id)
    if export is None:
        raise ApiError("INTERNAL_ERROR", "The export for this job no longer exists.")

    job.phase = JobPhase.packaging
    db.commit()

    try:
        build_export(db, export)
    except Exception as exc:
        from app.errors import sanitize_error_message

        export.state = ExportState.failed
        export.error_code = "EXPORT_FAILED"
        export.error_message = sanitize_error_message(exc)
        db.commit()
        raise

    job.result_export_id = export.id
    job.phase = None
    db.flush()
