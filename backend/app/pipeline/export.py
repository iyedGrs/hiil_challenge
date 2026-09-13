"""Reviewer package builder (spec/backend.md B10).

Produces one ZIP containing a summary PDF, an evidence index, the checks and
unresolved items, the original files and a manifest.

Everything is rendered from backend templates and stored validated data. There is
**no extra AI drafting call** (B10): a package is an assembly of what was already
validated, not a new piece of generated prose.

Three labelling rules the templates enforce, because a reviewer must be able to
tell these apart (B10):

* the preparer's **claim** is an allegation,
* a **documentary fact** is text quoted from an uploaded file,
* a preparer **explanation** is the preparer's own statement.

Disclosures travel with the package. ``legal_coverage=unvalidated`` and partial
coverage are stated in the summary and in the manifest, so a limitation cannot be
lost by opening the ZIP instead of the app.
"""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain.enums import AnalysisStatus, ExportState, FindingStatus, LegalCoverage
from app.errors import ApiError
from app.files import read_bytes, sha256_hex, write_bytes
from app.models.analysis import Analysis, CheckResultRow
from app.models.base import utcnow
from app.models.case import Case, ClaimRevision
from app.models.document import Document
from app.models.finding import Finding, FindingResponse
from app.models.job import Job
from app.models.legal import Check
from app.models.subject import Subject
from app.models.submission import Export

logger = logging.getLogger("app.pipeline.export")

#: Storage key template for a finished package.
EXPORT_KEY = "exports/{case_id}/{export_id}.zip"

#: Fixed disclaimer. Deliberately blunt: the package must not read as a legal
#: opinion, a certification or a court filing (B1, B10).
DISCLAIMER_LINES: tuple[str, ...] = (
    "Ce dossier est une preparation de documents. Il ne constitue ni un avis",
    "juridique, ni une certification, ni un depot devant une juridiction.",
    "Les verifications portent sur la presence, la lisibilite et la coherence",
    "interne des pieces fournies. Elles n'authentifient aucun document, ne",
    "determinent aucune responsabilite et n'evaluent aucun prejudice.",
)


def _wrap(text: str, width: int = 95) -> list[str]:
    """Wrap ``text`` to ``width`` characters, preserving word boundaries."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


class _Page:
    """Minimal flowing-text writer over a ReportLab canvas."""

    def __init__(self, pdf: canvas.Canvas) -> None:
        self.pdf = pdf
        self.width, self.height = A4
        self.y = self.height - 20 * mm

    def _ensure(self, needed: float = 6 * mm) -> None:
        if self.y - needed < 20 * mm:
            self.pdf.showPage()
            self.y = self.height - 20 * mm

    def heading(self, text: str) -> None:
        self._ensure(10 * mm)
        self.pdf.setFont("Helvetica-Bold", 12)
        self.pdf.drawString(20 * mm, self.y, text[:110])
        self.y -= 7 * mm

    def line(self, text: str, *, bold: bool = False, indent: float = 0.0) -> None:
        self.pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        for chunk in _wrap(text):
            self._ensure()
            self.pdf.drawString(20 * mm + indent, self.y, chunk)
            self.y -= 4.6 * mm

    def gap(self, amount: float = 3 * mm) -> None:
        self.y -= amount


def _summary_pdf(
    *,
    case: Case,
    claim: ClaimRevision,
    analysis: Analysis,
    rows: list[CheckResultRow],
    subjects: dict[str, Subject],
    definitions: dict[str, Check],
    responses: list[tuple[Finding, FindingResponse]],
    documents: list[Document],
) -> bytes:
    """Render the summary PDF (spec/backend.md B10)."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page = _Page(pdf)

    page.pdf.setFont("Helvetica-Bold", 15)
    page.pdf.drawString(20 * mm, page.y, "Dossier de preparation - litige commercial")
    page.y -= 10 * mm

    page.heading("Avertissement")
    for line in DISCLAIMER_LINES:
        page.line(line)
    page.gap()

    page.heading("Portee de l'analyse")
    page.line(f"Analyse : {analysis.id}")
    page.line(f"Revision du dossier : {analysis.revision}")
    page.line(f"Statut de l'analyse : {analysis.status.value}")
    page.line(f"Mode d'execution : {analysis.execution_mode.value}")
    page.line(f"Version du referentiel : {analysis.checklist_version}")
    page.line(f"Couverture juridique : {analysis.legal_coverage.value}")
    if analysis.legal_coverage is LegalCoverage.unvalidated:
        page.line(
            "Aucun referentiel juridique valide n'est disponible. Les verifications "
            "ci-dessous sont des controles documentaires, pas des exigences legales "
            "certifiees.",
            bold=True,
        )
    coverage = analysis.coverage or {}
    page.line(
        f"Pages examinees : {coverage.get('reviewed_pages', 0)} - "
        f"pages illisibles : {coverage.get('unreadable_pages', 0)} - "
        f"elements ecartes : {coverage.get('rejected_facts', 0)}"
    )
    if analysis.status is AnalysisStatus.partial:
        page.line(
            "Analyse partielle : une partie des pieces n'a pas pu etre examinee. "
            "L'absence d'un element ci-dessous n'est donc pas concluante.",
            bold=True,
        )
    page.gap()

    page.heading("Reclamation declaree par le preparateur (allegation)")
    page.line(f"Demandeur : {claim.claimant_name}")
    page.line(f"Partie adverse : {claim.counterparty_name}")
    page.line(f"Montant reclame : {claim.claimed_amount} {claim.currency.value}")
    page.line(f"Resultat demande : {claim.requested_outcome.value}")
    page.line(
        "Dates declarees - contrat : {} / livraison : {} / facture : {} / echeance : {}".format(
            claim.date_contract or "inconnue",
            claim.date_delivery or "inconnue",
            claim.date_invoice or "inconnue",
            claim.date_payment_due or "inconnue",
        )
    )
    page.line("Description declaree :")
    page.line(claim.narrative, indent=4 * mm)
    page.gap()

    if analysis.reconciliation:
        page.heading("Rapprochement calcule (code deterministe)")
        payload = analysis.reconciliation
        page.line(
            f"Solde d'apres les documents deposes : {payload['documented_balance']} "
            f"{payload['currency']}"
        )
        page.line(str(payload.get("coverage_note", "")))
        page.gap()

    page.heading("Verifications")
    for row in rows:
        subject = subjects.get(row.subject_id)
        definition = definitions.get(row.check_id)
        label = definition.label if definition else row.check_id
        page.line(f"[{row.result.value}] {label}", bold=True)
        page.line(f"Objet : {subject.label if subject else row.subject_id}", indent=4 * mm)
        page.line(f"Motif : {row.reason_code.value}", indent=4 * mm)
        page.line(row.message, indent=4 * mm)
        if row.finding_status is not None:
            page.line(f"Etat : {row.finding_status.value}", indent=4 * mm)
        for ref in row.evidence_refs:
            page.line(
                f"Fait documentaire - {ref['document_id']} p.{ref['page']} : "
                f"\"{str(ref['source_text'])[:200]}\"",
                indent=8 * mm,
            )
        page.gap(2 * mm)

    unresolved = [row for row in rows if row.finding_status is FindingStatus.open]
    page.gap()
    page.heading("Points non resolus")
    if not unresolved:
        page.line("Aucun point ouvert dans cette version.")
    for row in unresolved:
        definition = definitions.get(row.check_id)
        page.line(f"- {definition.label if definition else row.check_id}: {row.message}")

    if responses:
        page.gap()
        page.heading("Reponses du preparateur (declarations du preparateur)")
        for finding, response in responses:
            page.line(f"- {finding.check_id} / {finding.subject_id}: {response.action.value}")
            if response.explanation:
                page.line(response.explanation, indent=4 * mm)

    page.gap()
    page.heading("Index des pieces")
    for document in documents:
        page.line(
            f"- {document.display_name} ({document.page_count or 0} page(s), "
            f"{document.byte_size} octets, sha256 {document.sha256[:16]}...)"
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_export(db: DbSession, export: Export) -> None:
    """Assemble the ZIP for ``export`` and mark it ready (spec/backend.md B10).

    Raises:
        ApiError: when the analysis or case backing the export has gone missing.
    """
    from app.config import get_settings

    settings = get_settings()
    case = db.get(Case, export.case_id)
    analysis = db.get(Analysis, export.analysis_id)
    if case is None or analysis is None:  # pragma: no cover - FKs guarantee both
        raise ApiError("INTERNAL_ERROR", "The case or analysis for this export is missing.")

    claim = db.get(ClaimRevision, (case.id, analysis.revision)) or db.scalar(
        select(ClaimRevision)
        .where(ClaimRevision.case_id == case.id)
        .order_by(ClaimRevision.revision.desc())
        .limit(1)
    )
    if claim is None:  # pragma: no cover
        raise ApiError("INTERNAL_ERROR", "The claim revision for this export is missing.")

    rows = list(
        db.scalars(
            select(CheckResultRow).where(CheckResultRow.analysis_id == analysis.id)
        ).all()
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
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.id.in_(analysis.reviewed_document_ids or []))
            .order_by(Document.created_at)
        ).all()
    ) or list(
        db.scalars(
            select(Document)
            .where(Document.case_id == case.id, Document.is_active.is_(True))
            .order_by(Document.created_at)
        ).all()
    )
    responses = list(
        db.execute(
            select(Finding, FindingResponse)
            .join(FindingResponse, FindingResponse.finding_id == Finding.id)
            .where(Finding.case_id == case.id)
            .order_by(FindingResponse.created_at)
        ).all()
    )
    response_pairs = [(finding, response) for finding, response in responses]

    evidence_index = [
        {
            "document_id": document.id,
            "filename": document.display_name,
            "pages": document.page_count,
            "size_bytes": document.byte_size,
            "sha256": document.sha256,
            "mime_type": document.mime_type,
        }
        for document in documents
    ]
    checks_payload = [
        {
            "check_id": row.check_id,
            "subject_id": row.subject_id,
            "subject_label": (subjects[row.subject_id].label if row.subject_id in subjects else None),
            "result": row.result.value,
            "reason_code": row.reason_code.value,
            "finding_status": row.finding_status.value if row.finding_status else None,
            "basis": row.basis,
            "message": row.message,
            # Documentary facts, clearly separated from claim and explanation.
            "documentary_facts": row.evidence_refs,
            "legal_reference_ids": row.legal_reference_ids,
        }
        for row in rows
    ]
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
        "unresolved_count": sum(
            1 for row in rows if row.finding_status is FindingStatus.open
        ),
        "documents": evidence_index,
        "claim_is_an_allegation": True,
        "notice": (
            "Document preparation only. No legal advice, certification, "
            "authentication or court filing is implied."
        ),
    }

    summary = _summary_pdf(
        case=case,
        claim=claim,
        analysis=analysis,
        rows=rows,
        subjects=subjects,
        definitions=definitions,
        responses=response_pairs,
        documents=documents,
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("resume.pdf", summary)
        archive.writestr(
            "index_des_pieces.json", json.dumps(evidence_index, ensure_ascii=False, indent=2)
        )
        archive.writestr(
            "verifications.json", json.dumps(checks_payload, ensure_ascii=False, indent=2)
        )
        archive.writestr(
            "reponses_preparateur.json",
            json.dumps(
                [
                    {
                        "check_id": finding.check_id,
                        "subject_id": finding.subject_id,
                        "action": response.action.value,
                        "explanation_is_preparer_statement": True,
                        "explanation": response.explanation,
                        "document_ids": response.document_ids,
                        "created_at": response.created_at.isoformat(),
                    }
                    for finding, response in response_pairs
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )
        for document in documents:
            try:
                data = read_bytes(settings.file_storage_root, document.storage_key)
            except OSError:
                logger.warning("Original missing for document %s; noted in package", document.id)
                archive.writestr(
                    f"originaux/{document.id}.MANQUANT.txt",
                    "Le fichier original n'a pas pu etre lu au moment de la generation.",
                )
                continue
            archive.writestr(f"originaux/{document.id}-{document.display_name}", data)

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
