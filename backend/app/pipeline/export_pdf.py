"""Shared platypus rendering engine for the three export PDFs (spec/backend.md B10).

Pure rendering only: every function here takes already-decided plain strings and
returns PDF bytes. No database access and no business logic lives in this module
-- ``app/pipeline/export.py`` gathers and shapes the data.

Every user- or document-controlled string must be escaped with :func:`esc` (or
:func:`esc_br` for text with newlines) before it reaches a ``Paragraph`` -- that
is the only thing standing between a filename or narrative and broken/dangerous
markup, since Paragraph text is interpreted as a small XML dialect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

#: Placeholder constants shared by every renderer (spec export). Never invent
#: data to fill a gap -- these are the only two stand-ins allowed.
A_COMPLETER = "À compléter"
NON_RENSEIGNE = "Non renseigné"

_MARGIN = 20 * mm
_FRAME_WIDTH = A4[0] - 2 * _MARGIN
_HEADER_Y = A4[1] - 14 * mm
_FOOTER_PAGE_Y = 10 * mm
_FOOTER_NOTE_Y = 6 * mm

_NOTICE = (
    "Document préparatoire — non déposé ni accepté par une juridiction"
)

_STYLES = getSampleStyleSheet()
_STYLES.add(
    ParagraphStyle(name="XTitle", fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=8)
)
_STYLES.add(
    ParagraphStyle(
        name="XH2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=1,
    )
)
_STYLES.add(
    ParagraphStyle(
        name="XDocTitle",
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=1,
        spaceBefore=6,
        spaceAfter=10,
    )
)
_STYLES.add(
    ParagraphStyle(name="XCenter", fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=1)
)
_STYLES.add(ParagraphStyle(name="XBody", fontName="Helvetica", fontSize=9, leading=13))
_STYLES.add(ParagraphStyle(name="XBodyBold", fontName="Helvetica-Bold", fontSize=9, leading=13))
_STYLES.add(ParagraphStyle(name="XCell", fontName="Helvetica", fontSize=8, leading=10.5))
_STYLES.add(
    ParagraphStyle(
        name="XCellHeader",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
    )
)


def esc(text: object) -> str:
    """Escape ``text`` (coerced to ``str``) for safe use inside Paragraph markup."""
    return escape(str(text))


def esc_br(text: object) -> str:
    """Escape ``text`` and turn newlines into ``<br/>`` for Paragraph markup."""
    return esc(text).replace("\n", "<br/>")


def p(text: str, style: str = "XBody") -> Paragraph:
    """Build a ``Paragraph`` in one of the shared styles. ``text`` must already
    be escaped/marked-up by the caller."""
    return Paragraph(text, _STYLES[style])


def data_table(rows: list[list[Paragraph]], col_widths: list[float]) -> Table:
    """A bordered table with a repeating header row and wrapped cell text."""
    built = Table(rows, colWidths=col_widths, repeatRows=1)
    built.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return built


class _NumberedCanvas(canvas.Canvas):
    """Two-pass canvas: draws "Page X / Y" once the total page count is known."""

    def __init__(self, *args: object, case_reference: str, doc_title: str, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._case_reference = case_reference
        self._doc_title = doc_title
        self._saved_states: list[dict[str, object]] = []

    def showPage(self) -> None:  # noqa: N802 - reportlab's naming
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_chrome(total_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_chrome(self, total_pages: int) -> None:
        width, _ = A4
        self.setFont("Helvetica", 8)
        self.drawString(_MARGIN, _HEADER_Y, f"e-ethbet — {self._case_reference}")
        self.drawRightString(width - _MARGIN, _HEADER_Y, self._doc_title)
        self.setLineWidth(0.4)
        self.line(_MARGIN, _HEADER_Y - 3, width - _MARGIN, _HEADER_Y - 3)
        self.setFont("Helvetica", 8)
        self.drawCentredString(width / 2, _FOOTER_PAGE_Y, f"Page {self._pageNumber} / {total_pages}")
        self.setFont("Helvetica-Oblique", 7)
        self.drawCentredString(width / 2, _FOOTER_NOTE_Y, _NOTICE)


def _make_document(buffer: BytesIO, *, case_reference: str, doc_title: str) -> SimpleDocTemplate:
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN + 6 * mm,
        bottomMargin=_MARGIN + 4 * mm,
        title=doc_title,
        author="e-ethbet",
    )
    # canvasmaker is a build() argument; the constructor silently ignores it.
    doc.chrome = partial(_NumberedCanvas, case_reference=case_reference, doc_title=doc_title)
    return doc


def _signature_box(label: str) -> Table:
    box = Table([[p(esc(label), "XCell")]], colWidths=[60 * mm], rowHeights=[30 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return box


# --- 01. Requete introductive d'instance ------------------------------------


@dataclass
class ClaimPdfData:
    case_reference: str
    generated_at: str
    claimant_name: str
    counterparty_name: str
    invoice_reference: str
    claimed_amount: str
    currency: str
    requested_outcome_label: str
    narrative: str
    #: (date_display, event, source) rows, already sorted and deduplicated.
    chronology: list[tuple[str, str, str]]
    #: (piece_no, type_label, filename) rows, one per uploaded piece.
    evidence: list[tuple[int, str, str]]
    documented_balance_display: str
    reconciliation_currency: str
    coverage_note: str | None
    balance_mismatch_note: str | None


def render_claim_pdf(data: ClaimPdfData) -> bytes:
    """Render 01_requete_introductive_instance.pdf (spec export)."""
    buffer = BytesIO()
    doc = _make_document(
        buffer, case_reference=data.case_reference, doc_title="Requête introductive d’instance"
    )
    story: list[object] = [
        p("République Tunisienne", "XCenter"),
        p("REQUÊTE INTRODUCTIVE D’INSTANCE", "XDocTitle"),
        p(f"Tribunal : {esc(A_COMPLETER)}", "XBody"),
        p(f"Référence du dossier : {esc(data.case_reference)}", "XBody"),
        p(f"Date de génération : {esc(data.generated_at)}", "XBody"),
        Spacer(1, 6 * mm),
        p("Parties", "XH2"),
        p("<b>Demandeur</b>", "XBody"),
        p(f"Dénomination : {esc(data.claimant_name)}", "XBody"),
        p(f"Forme juridique : {esc(A_COMPLETER)}", "XBody"),
        p(f"Siège social / adresse : {esc(A_COMPLETER)}", "XBody"),
        p(f"Immatriculation (RNE / matricule fiscal) : {esc(A_COMPLETER)}", "XBody"),
        p(f"Avocat : {esc(A_COMPLETER)}", "XBody"),
        Spacer(1, 3 * mm),
        p("<b>Défendeur</b>", "XBody"),
        p(f"Dénomination : {esc(data.counterparty_name)}", "XBody"),
        p(f"Forme juridique : {esc(A_COMPLETER)}", "XBody"),
        p(f"Siège social / adresse : {esc(A_COMPLETER)}", "XBody"),
        p(f"Immatriculation (RNE / matricule fiscal) : {esc(A_COMPLETER)}", "XBody"),
        p(f"Avocat : {esc(A_COMPLETER)}", "XBody"),
        Spacer(1, 6 * mm),
        p("Objet de la demande", "XH2"),
        p("Demande de paiement d’une facture relative à une vente de marchandises", "XBody"),
        p(f"Référence de facture : {esc(data.invoice_reference)}", "XBody"),
        p(f"Montant réclamé : {esc(data.claimed_amount)} {esc(data.currency)}", "XBody"),
        p(f"Devise : {esc(data.currency)}", "XBody"),
        p(f"Résultat demandé : {esc(data.requested_outcome_label)}", "XBody"),
        Spacer(1, 6 * mm),
        p("Exposé des faits", "XH2"),
        p(esc_br(data.narrative), "XBody"),
    ]

    if data.chronology:
        story.append(Spacer(1, 3 * mm))
        story.append(p("Chronologie", "XBodyBold"))
        rows: list[list[Paragraph]] = [
            [p("Date", "XCellHeader"), p("Événement", "XCellHeader"), p("Source", "XCellHeader")]
        ]
        for date_display, event, source in data.chronology:
            rows.append([p(esc(date_display), "XCell"), p(esc(event), "XCell"), p(esc(source), "XCell")])
        story.append(data_table(rows, [35 * mm, 90 * mm, 45 * mm]))

    story.append(Spacer(1, 6 * mm))
    story.append(p("Moyens de preuve", "XH2"))
    for piece_no, type_label, filename in data.evidence:
        story.append(
            p(f"Pièce P{piece_no:02d} — {esc(type_label)} — {esc(filename)}", "XBody")
        )

    story.append(Spacer(1, 6 * mm))
    story.append(p("Rapprochement financier", "XH2"))
    balance_cell = (
        esc(f"{data.documented_balance_display} {data.reconciliation_currency}")
        if data.coverage_note is not None
        else esc(data.documented_balance_display)
    )
    reco_rows = [
        [p("Poste", "XCellHeader"), p("Montant", "XCellHeader")],
        [p("Solde documenté", "XCell"), p(balance_cell, "XCell")],
        [p("Montant réclamé", "XCell"), p(esc(f"{data.claimed_amount} {data.currency}"), "XCell")],
        [p("Devise", "XCell"), p(esc(data.currency), "XCell")],
        [p("Total facture", "XCell"), p(esc(NON_RENSEIGNE), "XCell")],
        [p("Paiements", "XCell"), p(esc(NON_RENSEIGNE), "XCell")],
        [p("Notes de crédit", "XCell"), p(esc(NON_RENSEIGNE), "XCell")],
    ]
    story.append(data_table(reco_rows, [90 * mm, 80 * mm]))
    story.append(Spacer(1, 2 * mm))
    if data.coverage_note is not None:
        story.append(p(f"Note du rapprochement : {esc(data.coverage_note)}", "XBody"))
    else:
        story.append(p("Aucun rapprochement n’a pu être établi à partir des pièces.", "XBody"))
    if data.balance_mismatch_note:
        story.append(p(esc(data.balance_mismatch_note), "XBody"))

    story.append(Spacer(1, 6 * mm))
    story.append(p("Prétentions du demandeur", "XH2"))
    story.append(
        p(
            "Le demandeur sollicite le paiement du montant déclaré dans le présent "
            "dossier, sous réserve de l’appréciation de la juridiction compétente.",
            "XBody",
        )
    )
    story.append(p(f"Montant : {esc(data.claimed_amount)} {esc(data.currency)}", "XBody"))

    story.append(Spacer(1, 6 * mm))
    story.append(p("Fondement juridique", "XH2"))
    story.append(p(f"Fondement juridique : {esc(A_COMPLETER)}", "XBody"))

    story.append(Spacer(1, 10 * mm))
    story.append(p(f"Fait à : {esc(A_COMPLETER)}, le {esc(data.generated_at)}", "XBody"))
    story.append(p(f"Avocat : {esc(A_COMPLETER)}", "XBody"))
    story.append(Spacer(1, 4 * mm))
    story.append(KeepTogether(_signature_box("Signature")))

    doc.build(story, canvasmaker=doc.chrome)
    return buffer.getvalue()


# --- 02. Bordereau des pieces -------------------------------------------------


@dataclass
class BordereauRow:
    piece_no: int
    type_label: str
    reference: str
    date_display: str
    filename: str
    pages: str


@dataclass
class BordereauPdfData:
    case_reference: str
    generated_at: str
    claimant_name: str
    counterparty_name: str
    rows: list[BordereauRow]


def render_bordereau_pdf(data: BordereauPdfData) -> bytes:
    """Render 02_bordereau_des_pieces.pdf (spec export)."""
    buffer = BytesIO()
    doc = _make_document(buffer, case_reference=data.case_reference, doc_title="Bordereau des pièces")
    story: list[object] = [
        p("BORDEREAU DES PIÈCES", "XDocTitle"),
        p(f"Référence du dossier : {esc(data.case_reference)}", "XBody"),
        p(f"Demandeur : {esc(data.claimant_name)}", "XBody"),
        p(f"Défendeur : {esc(data.counterparty_name)}", "XBody"),
        p(f"Date de génération : {esc(data.generated_at)}", "XBody"),
        Spacer(1, 6 * mm),
    ]
    rows: list[list[Paragraph]] = [
        [
            p("N°", "XCellHeader"),
            p("Type de document", "XCellHeader"),
            p("Référence", "XCellHeader"),
            p("Date", "XCellHeader"),
            p("Nom du fichier", "XCellHeader"),
            p("Pages", "XCellHeader"),
        ]
    ]
    for row in data.rows:
        rows.append(
            [
                p(f"P{row.piece_no:02d}", "XCell"),
                p(esc(row.type_label), "XCell"),
                p(esc(row.reference), "XCell"),
                p(esc(row.date_display), "XCell"),
                p(esc(row.filename), "XCell"),
                p(esc(row.pages), "XCell"),
            ]
        )
    story.append(data_table(rows, [12 * mm, 30 * mm, 30 * mm, 21 * mm, 65 * mm, 12 * mm]))
    doc.build(story, canvasmaker=doc.chrome)
    return buffer.getvalue()


# --- 03. Resume de verification ----------------------------------------------


@dataclass
class CheckRowData:
    header: str
    subject_line: str
    reason_line: str
    message: str
    status_line: str | None
    evidence_lines: list[str] = field(default_factory=list)


@dataclass
class SummaryPdfData:
    case_reference: str
    generated_at: str
    verdict_line: str
    verdict_reasons: list[str]
    disclaimer_lines: list[str]
    scope_lines: list[str]
    partial_warning: str | None
    claim_lines: list[str]
    narrative: str
    reconciliation_lines: list[str] | None
    checks: list[CheckRowData]
    unresolved_lines: list[str]
    response_lines: list[tuple[str, str | None]]
    #: (piece_no, description) rows, already using the shared P-numbers.
    evidence_index: list[tuple[int, str]]


def render_summary_pdf(data: SummaryPdfData) -> bytes:
    """Render 03_resume_verification.pdf (spec export)."""
    buffer = BytesIO()
    doc = _make_document(
        buffer, case_reference=data.case_reference, doc_title="Résumé de vérification"
    )
    story: list[object] = [
        p("RÉSUMÉ DE VÉRIFICATION", "XDocTitle"),
        p("Dossier de préparation — litige commercial", "XCenter"),
        Spacer(1, 4 * mm),
        p(esc(data.verdict_line), "XBodyBold"),
    ]
    for reason in data.verdict_reasons:
        story.append(p(f"– {esc(reason)}", "XBody"))
    story.append(Spacer(1, 4 * mm))

    story.append(p("Avertissement", "XH2"))
    story.append(p(esc_br("\n".join(data.disclaimer_lines)), "XBody"))
    story.append(Spacer(1, 4 * mm))

    story.append(p("Portée de l'analyse", "XH2"))
    for line in data.scope_lines:
        story.append(p(esc(line), "XBody"))
    if data.partial_warning:
        story.append(p(esc(data.partial_warning), "XBodyBold"))
    story.append(Spacer(1, 4 * mm))

    story.append(p("Réclamation déclarée par le préparateur (allégation)", "XH2"))
    for line in data.claim_lines:
        story.append(p(esc(line), "XBody"))
    story.append(p("Description déclarée :", "XBody"))
    story.append(p(esc_br(data.narrative), "XBody"))
    story.append(Spacer(1, 4 * mm))

    if data.reconciliation_lines:
        story.append(p("Rapprochement calculé (code déterministe)", "XH2"))
        for line in data.reconciliation_lines:
            story.append(p(esc(line), "XBody"))
        story.append(Spacer(1, 4 * mm))

    heading: list[object] = [p("Vérifications", "XH2")]
    for check in data.checks:
        block: list[object] = [
            p(esc(check.header), "XBodyBold"),
            p(esc(check.subject_line), "XBody"),
            p(esc(check.reason_line), "XBody"),
            p(esc(check.message), "XBody"),
        ]
        if check.status_line:
            block.append(p(esc(check.status_line), "XBody"))
        for line in check.evidence_lines:
            block.append(p(esc(line), "XBody"))
        block.append(Spacer(1, 2 * mm))
        # The heading travels with the first check so it is never stranded.
        story.append(KeepTogether(heading + block))
        heading = []
    story.extend(heading)

    story.append(Spacer(1, 4 * mm))
    story.append(p("Points non résolus", "XH2"))
    if not data.unresolved_lines:
        story.append(p("Aucun point ouvert dans cette version.", "XBody"))
    for line in data.unresolved_lines:
        story.append(p(esc(line), "XBody"))

    if data.response_lines:
        story.append(Spacer(1, 4 * mm))
        story.append(p("Réponses du préparateur (déclarations du préparateur)", "XH2"))
        for header, explanation in data.response_lines:
            story.append(p(esc(header), "XBody"))
            if explanation:
                story.append(p(esc(explanation), "XBody"))

    story.append(Spacer(1, 4 * mm))
    story.append(p("Index des pièces", "XH2"))
    for piece_no, description in data.evidence_index:
        story.append(p(f"Pièce P{piece_no:02d} — {esc(description)}", "XBody"))

    doc.build(story, canvasmaker=doc.chrome)
    return buffer.getvalue()
