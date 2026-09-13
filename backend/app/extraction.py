"""Page registry extraction: embedded text and OCR (spec/backend.md B4).

Builds the immutable per-page text registry synchronously during upload. For a
PDF, each page first tries embedded text (``pdfplumber``); a page with no usable
embedded text is treated as a scan and rendered with ``pypdfium2`` then read
with ``pytesseract`` OCR. A JPEG/PNG upload is always a single OCR'd page.

Quality heuristic (documented here because the spec leaves the exact thresholds
to implementation judgment):

* ``ready`` — embedded text with a non-trivial character count, or OCR text
  that clears :data:`OCR_READY_CHAR_THRESHOLD` characters.
* ``partial`` — some text was recovered (OCR or embedded) but it is short
  enough that a human should not fully trust completeness (below
  :data:`OCR_READY_CHAR_THRESHOLD` but at/above :data:`PARTIAL_CHAR_THRESHOLD`).
* ``unreadable`` — no usable text at all (empty/near-empty after OCR, or OCR
  could not run, e.g. the Tesseract binary is missing in this environment).

None of this is a claim about scan authenticity or OCR correctness (B4); it is
only a cheap, deterministic signal about how much text was recovered.

The OCR path never lets a missing system binary crash the request: pytesseract
raises ``TesseractNotFoundError`` when the ``tesseract`` executable is absent,
which is caught here and turned into an ``unreadable`` page with a sanitized
message, exactly like a genuinely unreadable scan.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import Image
from pdfminer.pdftypes import PDFException

from app.domain.enums import PageMethod, PageState

logger = logging.getLogger("app.extraction")

#: Version tag stored on every page/document produced by this extraction code.
#: Bumping this invalidates nothing automatically (page text is immutable, B7);
#: it exists so a future extraction change can be told apart from this one.
EXTRACTION_VERSION = "v1"

#: Render resolution for OCR: ~200 DPI (scale is relative to the 72-DPI PDF unit).
OCR_RENDER_SCALE = 200 / 72

#: Quality thresholds on recovered character count (see module docstring).
OCR_READY_CHAR_THRESHOLD = 40
PARTIAL_CHAR_THRESHOLD = 5

#: Cap on rendered pixels per page, a bounded-resource guard (spec/backend.md B4
#: "page/pixel/resource limits during parsing").
MAX_RENDER_PIXELS = 4000 * 4000


class UnparseableDocumentError(Exception):
    """Raised when a whole document cannot be opened at all (B4).

    Covers encrypted PDFs and structurally invalid files. Callers reject the
    upload with a targeted error rather than storing a page registry.
    """


@dataclass
class ExtractedPage:
    """One page ready to persist as a :class:`app.models.document.Page` row."""

    page_number: int
    text: str
    method: PageMethod
    state: PageState
    char_count: int
    quality: dict[str, object] = field(default_factory=dict)
    image_bytes: bytes | None = None


@dataclass
class ExtractionResult:
    """Full per-document outcome of building the page registry."""

    pages: list[ExtractedPage]


def _classify(char_count: int, *, ocr_failed: bool) -> PageState:
    """Apply the quality heuristic documented in the module docstring."""
    if ocr_failed or char_count < PARTIAL_CHAR_THRESHOLD:
        return PageState.unreadable
    if char_count < OCR_READY_CHAR_THRESHOLD:
        return PageState.partial
    return PageState.ready


def _ocr_image(image: Image.Image, languages: str) -> tuple[str, dict[str, object]]:
    """Run Tesseract OCR over ``image``.

    Returns ``(text, quality)``. Any failure to actually run OCR (most notably
    the ``tesseract`` binary being absent from this environment) is reported
    through ``quality["ocr_error"]`` with a sanitized message rather than
    propagating, so a missing local install degrades to an unreadable page
    instead of a crashed request.
    """
    try:
        text = pytesseract.image_to_string(image, lang=languages)
    except Exception as exc:  # noqa: BLE001 - OCR backends raise many types
        logger.warning("OCR unavailable: %s", type(exc).__name__)
        return "", {"ocr_error": type(exc).__name__}
    return text, {}


def _render_pdf_page_to_image(page: "pdfium.PdfPage") -> Image.Image:
    width, height = page.get_size()
    scale = OCR_RENDER_SCALE
    if width * height * scale * scale > MAX_RENDER_PIXELS:
        scale = max(1.0, (MAX_RENDER_PIXELS / (width * height)) ** 0.5)
    bitmap = page.render(scale=scale)
    return bitmap.to_pil().convert("RGB")


def extract_pdf_pages(data: bytes, *, ocr_languages: str) -> ExtractionResult:
    """Build the page registry for a PDF upload.

    Each page tries embedded text first; a page with no usable embedded text is
    rendered and OCR'd (B4). Raises :class:`UnparseableDocumentError` when the
    PDF cannot be opened at all (encrypted or structurally invalid).
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as plumber_pdf:
            embedded_texts = [pg.extract_text() or "" for pg in plumber_pdf.pages]
    except PDFException as exc:
        raise UnparseableDocumentError(type(exc).__name__) from exc
    except Exception as exc:  # noqa: BLE001 - any other parser failure is fatal
        raise UnparseableDocumentError(type(exc).__name__) from exc

    try:
        pdfium_doc = pdfium.PdfDocument(data)
    except Exception as exc:  # noqa: BLE001 - pdfium raises its own error types
        raise UnparseableDocumentError(type(exc).__name__) from exc

    pages: list[ExtractedPage] = []
    try:
        for index, embedded_text in enumerate(embedded_texts):
            page_number = index + 1
            stripped = embedded_text.strip()
            if len(stripped) >= PARTIAL_CHAR_THRESHOLD:
                # Usable embedded text: no OCR needed for this page.
                char_count = len(stripped)
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=embedded_text,
                        method=PageMethod.embedded_text,
                        state=_classify(char_count, ocr_failed=False),
                        char_count=char_count,
                        quality={"char_count": char_count, "source": "embedded_text"},
                    )
                )
                continue

            # Scanned page: render and OCR.
            pdfium_page = pdfium_doc[index]
            image = _render_pdf_page_to_image(pdfium_page)
            ocr_text, ocr_quality = _ocr_image(image, ocr_languages)
            char_count = len(ocr_text.strip())
            image_bytes: bytes | None = None
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            quality = {"char_count": char_count, "source": "ocr", **ocr_quality}
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    text=ocr_text,
                    method=PageMethod.ocr,
                    state=_classify(char_count, ocr_failed="ocr_error" in ocr_quality),
                    char_count=char_count,
                    quality=quality,
                    image_bytes=image_bytes,
                )
            )
    finally:
        pdfium_doc.close()

    return ExtractionResult(pages=pages)


def extract_image_page(data: bytes, *, ocr_languages: str) -> ExtractionResult:
    """Build the single-page registry for a JPEG/PNG upload (B4)."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - Pillow raises many decode errors
        raise UnparseableDocumentError(type(exc).__name__) from exc

    ocr_text, ocr_quality = _ocr_image(image, ocr_languages)
    char_count = len(ocr_text.strip())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    quality = {"char_count": char_count, "source": "ocr", **ocr_quality}
    page = ExtractedPage(
        page_number=1,
        text=ocr_text,
        method=PageMethod.ocr,
        state=_classify(char_count, ocr_failed="ocr_error" in ocr_quality),
        char_count=char_count,
        quality=quality,
        image_bytes=buffer.getvalue(),
    )
    return ExtractionResult(pages=[page])


def document_state_from_pages(states: list[PageState]) -> PageState:
    """Roll per-page states into the document-level state (B4).

    ``ready`` only when every page is ready; ``unreadable`` only when none is
    usable; otherwise ``partial`` (at least one usable page, but not all).
    """
    if not states:
        return PageState.unreadable
    if all(state is PageState.ready for state in states):
        return PageState.ready
    if all(state is PageState.unreadable for state in states):
        return PageState.unreadable
    return PageState.partial
