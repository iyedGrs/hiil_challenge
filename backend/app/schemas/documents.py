"""Document/page schemas (spec/backend.md B4, B9).

Covers ``POST/DELETE /api/cases/{id}/documents*`` and
``GET /api/documents/{id}/pages/{page}``. IDs are opaque strings, timestamps are
UTC ISO 8601, and no raw parser output or document content ever appears here
(B9).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.enums import DocumentState, PageMethod, PageState
from app.schemas.common import ResponseModel


class DocumentOut(ResponseModel):
    """Public view of a :class:`app.models.document.Document` row (B4, B9)."""

    id: str
    case_id: str
    display_name: str
    mime_type: str
    byte_size: int
    page_count: int | None
    state: DocumentState
    is_active: bool
    rejection_code: str | None
    rejection_message: str | None
    added_revision: int
    detached_revision: int | None
    created_at: datetime
    detached_at: datetime | None


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

    Text and quality metadata only; a rendered image is exposed as a pointer
    (``image_key`` presence), not inline bytes, in this slice.
    """

    id: str
    document_id: str
    page_number: int
    text: str
    method: PageMethod
    state: PageState
    char_count: int
    extraction_version: str
    quality: dict[str, object]
    has_image: bool
