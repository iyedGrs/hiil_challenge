"""Document/page schemas (spec/backend.md B4, B9).

Covers ``POST/DELETE /api/cases/{id}/documents*`` and
``GET /api/documents/{id}/pages/{page}``. IDs are opaque strings, timestamps are
UTC ISO 8601, and no raw parser output or document content ever appears here
beyond the stored page text the preparer is authorized to read (B9).

Field names are the ones the UI consumes (``frontend/src/api/types.ts``
``DocumentRecord`` / ``DocumentPage``). They deliberately differ from the column
names: the wire contract talks about a document the way a preparer sees it
(``filename``, ``pages``, ``active``, ``error``) while the model keeps storage
vocabulary (``display_name``, ``page_count``, ``is_active``,
``rejection_message``).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.enums import DocumentState, PageMethod
from app.schemas.common import ResponseModel


class DocumentOut(ResponseModel):
    """Public view of a :class:`app.models.document.Document` row (B4, B9).

    ``state`` never implies authenticity: ``ready`` means the page text could be
    read, nothing more (B4, frontend.md F4).
    """

    document_id: str
    filename: str
    #: Server-classified document type once extraction has run; null until then.
    #: Never client-supplied.
    document_type: str | None
    #: Page count, null while the registry has not been built.
    pages: int | None
    uploaded_at: datetime
    state: DocumentState
    #: Sanitized reason a file was rejected; never a parser trace (B9).
    error: str | None
    #: False once detached from the working case. The row and bytes survive so a
    #: submitted snapshot stays accessible (B10).
    active: bool
    size_bytes: int


class UploadDocumentOut(ResponseModel):
    """``POST /api/cases/{id}/documents`` response (B9).

    ``duplicate=true`` means ``(case_id, sha256)`` already existed for this
    case; no new active file was created and ``revision`` is unchanged.
    """

    duplicate: bool
    document: DocumentOut
    revision: int


class DeleteDocumentOut(ResponseModel):
    """``DELETE /api/cases/{id}/documents/{document_id}`` response (B9)."""

    document: DocumentOut
    revision: int


class PageOut(ResponseModel):
    """``GET /api/documents/{id}/pages/{page}`` response (B4, B9).

    ``source_text`` is the immutable stored page text that published citations
    are validated against (B7). ``quality`` is the page's readability outcome
    (``ready``/``partial``/``unreadable``) as a short label, kept separate from
    citation-match status: a quote match proves correspondence to stored text,
    not scan authenticity or OCR correctness (B4).

    ``image_url`` points at the authorized rendered-page route when a rendered
    image exists (scans), and is null for pages read from embedded PDF text.
    """

    document_id: str
    page: int
    image_url: str | None
    source_text: str | None
    method: PageMethod | None
    quality: str | None
