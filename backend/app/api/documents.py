"""Document ingestion and access routes (spec/backend.md B4, B9).

Covers ``POST/DELETE /api/cases/{id}/documents*`` and the authorized
``GET /api/documents/{id}/...`` read routes. Every route requires the
signed-in user to own the case; an inaccessible or unknown case/document
answers 404, never 403, so existence is not disclosed (B8, B9).

Upload enforces limits before any expensive parsing (file count, per-file
bytes, case-wide bytes), then builds the page registry synchronously and
enforces the total-page cap once the real page count is known. A row lock on
the case (``SELECT ... FOR UPDATE``) is held for the whole request so a stale
``expected_revision`` is rejected atomically and concurrent uploads on the same
case serialise rather than race (B4, B9).
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile
from sqlalchemy import func, select

from app.api.deps import CsrfDep, DbDep, PreparerDep
from app.config import get_settings
from app.domain.enums import DocumentState
from app.errors import FILE_LIMIT, REVISION_CONFLICT, UNSUPPORTED_FILE, ApiError, not_found
from app.extraction import (
    EXTRACTION_VERSION,
    ExtractionResult,
    UnparseableDocumentError,
    document_state_from_pages,
    extract_image_page,
    extract_pdf_pages,
)
from app.files import (
    MAGIC_SNIFF_BYTES,
    extension_for_mime,
    new_image_key,
    new_storage_key,
    read_bytes,
    sanitize_display_name,
    sha256_hex,
    sniff_mime_type,
    write_bytes,
)
from app.ids import DOCUMENT_PREFIX, PAGE_PREFIX, new_id
from app.models.base import utcnow
from app.models.case import Case
from app.models.document import Document, Page
from app.models.user import User
from app.schemas.documents import DeleteDocumentOut, DocumentOut, PageOut, UploadDocumentOut

logger = logging.getLogger("app.api.documents")

router = APIRouter(tags=["documents"])

#: Sanitized rejection code stored on the row for an encrypted/unparseable file.
#: The HTTP-level error code is still ``UNSUPPORTED_FILE`` (415, B9); this value
#: is a more specific reason surfaced to the UI on the stored row (B4).
REJECTION_ENCRYPTED_OR_UNREADABLE = "ENCRYPTED_OR_UNREADABLE"

#: Bounded read chunk size while enforcing the per-file byte limit (B4).
READ_CHUNK_BYTES = 65_536


def _load_owned_case(db: DbDep, case_id: str, user: User, *, lock: bool) -> Case:
    """Return the case owned by ``user``, or raise 404 without disclosing it.

    ``lock`` takes a ``SELECT ... FOR UPDATE`` so the revision check and the
    eventual bump/detach happen atomically within one transaction (B9).
    """
    stmt = select(Case).where(Case.id == case_id)
    if lock:
        stmt = stmt.with_for_update()
    case = db.scalar(stmt)
    if case is None or case.owner_id != user.id:
        raise not_found()
    return case


def _require_matching_revision(case: Case, expected_revision: int) -> None:
    """Raise 409 ``REVISION_CONFLICT`` when ``expected_revision`` is stale (B9)."""
    if case.revision != expected_revision:
        raise ApiError(
            REVISION_CONFLICT,
            "The case has changed since this revision was read.",
        )


def _document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        case_id=document.case_id,
        display_name=document.display_name,
        mime_type=document.mime_type,
        byte_size=document.byte_size,
        page_count=document.page_count,
        state=document.state,
        is_active=document.is_active,
        rejection_code=document.rejection_code,
        rejection_message=document.rejection_message,
        added_revision=document.added_revision,
        detached_revision=document.detached_revision,
        created_at=document.created_at,
        detached_at=document.detached_at,
    )


async def _read_upload(file: UploadFile, max_file_bytes: int) -> tuple[bytes, str | None]:
    """Read ``file`` up to ``max_file_bytes`` and sniff its content signature.

    Returns ``(data, sniffed_mime)``. Reading stops as soon as the byte budget
    is exceeded so an oversized upload never has to be fully buffered
    (spec/backend.md B4: "Enforce byte limits while reading").

    Raises:
        ApiError: 413 ``FILE_LIMIT`` once more than ``max_file_bytes`` has been
            read.
    """
    chunks: list[bytes] = []
    total = 0
    sniffed: str | None = None
    while True:
        chunk = await file.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        if sniffed is None and total + len(chunk) >= MAGIC_SNIFF_BYTES:
            head = b"".join(chunks) + chunk
            sniffed = sniff_mime_type(head[:MAGIC_SNIFF_BYTES]) or ""
        total += len(chunk)
        if total > max_file_bytes:
            raise ApiError(
                FILE_LIMIT,
                "The file exceeds the maximum allowed size.",
            )
        chunks.append(chunk)
    if sniffed is None:
        # File shorter than the sniff window: sniff whatever was read.
        sniffed = sniff_mime_type(b"".join(chunks)) or ""
    return b"".join(chunks), (sniffed or None)


def _active_document_totals(db: DbDep, case_id: str) -> tuple[int, int, int]:
    """Return ``(active_file_count, active_byte_total, active_page_total)``."""
    row = db.execute(
        select(
            func.count(Document.id),
            func.coalesce(func.sum(Document.byte_size), 0),
            func.coalesce(func.sum(Document.page_count), 0),
        ).where(Document.case_id == case_id, Document.is_active.is_(True))
    ).one()
    return int(row[0]), int(row[1]), int(row[2])


def _find_duplicate(db: DbDep, case_id: str, sha256: str) -> Document | None:
    """Return the existing row for ``(case_id, sha256)``, if any (B9).

    ``(case_id, sha256)`` is unique on the table, so at most one row can match
    regardless of its active/rejected state (spec/backend.md B9: "Scope
    duplicate lookup to this authorized case.").
    """
    return db.scalar(
        select(Document).where(Document.case_id == case_id, Document.sha256 == sha256)
    )


def _run_extraction(mime_type: str, data: bytes, ocr_languages: str) -> ExtractionResult:
    """Dispatch to the PDF or image extraction path (B4)."""
    if mime_type == "application/pdf":
        return extract_pdf_pages(data, ocr_languages=ocr_languages)
    return extract_image_page(data, ocr_languages=ocr_languages)


@router.post(
    "/cases/{case_id}/documents",
    response_model=UploadDocumentOut,
    status_code=201,
    summary="Upload an original file to a case",
)
async def upload_document(
    case_id: str,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
    response: Response,
    file: UploadFile = File(...),
    expected_revision: int = Form(...),
) -> UploadDocumentOut:
    """``POST /api/cases/{id}/documents`` (spec/backend.md B4, B9).

    Order of checks, all before the expensive page-registry build except the
    total-page cap (which needs the real page count):

    1. Case ownership and row lock, then the ``expected_revision`` check.
    2. Content-signature sniff against the supported MIME allow-list, enforced
       while reading so an oversized upload never has to be fully buffered
       (``max_file_bytes``).
    3. Duplicate lookup by ``(case_id, sha256)``. A duplicate is a no-op --
       it creates no new active file and consumes no budget -- so it is
       resolved *before* the file-count/byte-cap checks below, which only
       matter for a genuinely new active file.
    4. Active file count (``max_case_files``) and case-wide byte cap
       (``max_case_bytes``).
    5. Page-registry extraction; an encrypted/unparseable file is stored as a
       ``rejected`` row (still visible, never silently dropped) and answers
       415. A page-count overflow answers 413 without storing anything.
    """
    settings = get_settings()
    case = _load_owned_case(db, case_id, user, lock=True)
    _require_matching_revision(case, expected_revision)

    data, sniffed_mime = await _read_upload(file, settings.max_file_bytes)
    if sniffed_mime not in settings.supported_mime_types:
        raise ApiError(
            UNSUPPORTED_FILE,
            "Only PDF, JPEG and PNG files are supported.",
        )
    mime_type = sniffed_mime
    byte_size = len(data)

    sha256 = sha256_hex(data)
    duplicate = _find_duplicate(db, case.id, sha256)
    if duplicate is not None:
        # 200, not the route's default 201: no new active file/revision was
        # created (spec/backend.md B9).
        response.status_code = 200
        return UploadDocumentOut(duplicate=True, document=_document_out(duplicate), revision=case.revision)

    active_files, active_bytes, active_pages = _active_document_totals(db, case.id)
    if active_files >= settings.max_case_files:
        raise ApiError(FILE_LIMIT, "This case already has the maximum number of files.")
    if active_bytes + byte_size > settings.max_case_bytes:
        raise ApiError(FILE_LIMIT, "This case has reached its total storage limit.")

    display_name = sanitize_display_name(file.filename)
    document_id = new_id(DOCUMENT_PREFIX)
    storage_key = new_storage_key(case.id, extension_for_mime(mime_type))

    try:
        result = _run_extraction(mime_type, data, settings.ocr_languages)
    except UnparseableDocumentError as exc:
        write_bytes(settings.file_storage_root, storage_key, data)
        rejected = Document(
            id=document_id,
            case_id=case.id,
            display_name=display_name,
            storage_key=storage_key,
            mime_type=mime_type,
            byte_size=byte_size,
            sha256=sha256,
            page_count=None,
            state=DocumentState.rejected,
            is_active=False,
            rejection_code=REJECTION_ENCRYPTED_OR_UNREADABLE,
            # Sanitized: the exception type only, never a parser traceback or
            # document content (spec/backend.md B9).
            rejection_message=f"The file could not be read ({type(exc).__name__}).",
            extraction_version=EXTRACTION_VERSION,
            added_revision=case.revision,
            uploaded_by=user.id,
        )
        db.add(rejected)
        # Commit now so the rejected row survives the exception below: B4
        # requires storing it, not silently dropping it, even though the
        # request itself answers an error.
        db.commit()
        raise ApiError(UNSUPPORTED_FILE, "The file is encrypted or could not be read.") from exc

    new_page_total = active_pages + len(result.pages)
    if new_page_total > settings.max_case_pages:
        raise ApiError(
            FILE_LIMIT,
            "This case has reached its total page limit.",
        )

    write_bytes(settings.file_storage_root, storage_key, data)

    page_states = [page.state for page in result.pages]
    document_state = DocumentState(document_state_from_pages(page_states).value)
    new_revision = case.revision + 1
    case.revision = new_revision

    document = Document(
        id=document_id,
        case_id=case.id,
        display_name=display_name,
        storage_key=storage_key,
        mime_type=mime_type,
        byte_size=byte_size,
        sha256=sha256,
        page_count=len(result.pages),
        state=document_state,
        is_active=True,
        extraction_version=EXTRACTION_VERSION,
        added_revision=new_revision,
        uploaded_by=user.id,
    )
    db.add(document)

    for extracted in result.pages:
        image_key: str | None = None
        if extracted.image_bytes is not None:
            image_key = new_image_key(case.id, document_id, extracted.page_number)
            write_bytes(settings.file_storage_root, image_key, extracted.image_bytes)
        db.add(
            Page(
                id=new_id(PAGE_PREFIX),
                document_id=document_id,
                case_id=case.id,
                page_number=extracted.page_number,
                text=extracted.text,
                method=extracted.method,
                state=extracted.state,
                quality=extracted.quality,
                extraction_version=EXTRACTION_VERSION,
                image_key=image_key,
                char_count=extracted.char_count,
            )
        )

    db.flush()
    return UploadDocumentOut(duplicate=False, document=_document_out(document), revision=new_revision)


@router.delete(
    "/cases/{case_id}/documents/{document_id}",
    response_model=DeleteDocumentOut,
    summary="Detach an active document from a case",
)
def delete_document(
    case_id: str,
    document_id: str,
    expected_revision: int,
    user: PreparerDep,
    db: DbDep,
    _csrf: CsrfDep,
) -> DeleteDocumentOut:
    """``DELETE /api/cases/{id}/documents/{document_id}`` (B9).

    Detaches an *active* file: ``is_active`` is cleared and ``detached_at``/
    ``detached_revision`` are set. The row is never deleted, so a previously
    submitted snapshot referencing it stays reachable (B10). A document that is
    unknown, belongs to another case/owner, or is already inactive answers 404
    without distinguishing those cases (B9).
    """
    case = _load_owned_case(db, case_id, user, lock=True)
    _require_matching_revision(case, expected_revision)

    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.case_id == case.id)
    )
    if document is None or not document.is_active:
        raise not_found()

    new_revision = case.revision + 1
    case.revision = new_revision
    document.is_active = False
    document.detached_at = utcnow()
    document.detached_revision = new_revision

    db.flush()
    return DeleteDocumentOut(document=_document_out(document), revision=new_revision)


def _load_owned_document(db: DbDep, document_id: str, user: User) -> Document:
    """Return ``document_id`` when its case is owned by ``user``, else 404 (B9)."""
    document = db.scalar(
        select(Document)
        .join(Case, Case.id == Document.case_id)
        .where(Document.id == document_id, Case.owner_id == user.id)
    )
    if document is None:
        raise not_found()
    return document


@router.get(
    "/documents/{document_id}/content",
    summary="Download or preview the original bytes of a document",
)
def get_document_content(document_id: str, user: PreparerDep, db: DbDep) -> Response:
    """``GET /api/documents/{id}/content`` (B9): authorized original bytes.

    ``Content-Disposition: inline`` lets the browser preview PDFs/images
    directly; the sanitized display name is offered as the suggested filename
    via the RFC 5987 ``filename*`` form so it can safely carry non-ASCII text
    (Arabic display names are common in this dataset) without header
    injection risk.
    """
    settings = get_settings()
    document = _load_owned_document(db, document_id, user)
    data = read_bytes(settings.file_storage_root, document.storage_key)
    encoded_name = quote(document.display_name)
    disposition = f"inline; filename*=UTF-8''{encoded_name}"
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/documents/{document_id}/pages/{page_number}",
    response_model=PageOut,
    summary="Read one page's stored text and quality metadata",
)
def get_document_page(
    document_id: str, page_number: int, user: PreparerDep, db: DbDep
) -> PageOut:
    """``GET /api/documents/{id}/pages/{page}`` (B4, B9).

    Returns the immutable stored page text and quality metadata. Image bytes
    are not served in this slice; ``has_image`` tells the caller whether a
    rendered page image exists in storage for a future preview endpoint.
    """
    document = _load_owned_document(db, document_id, user)
    page = db.scalar(
        select(Page).where(Page.document_id == document.id, Page.page_number == page_number)
    )
    if page is None:
        raise not_found()
    return PageOut(
        id=page.id,
        document_id=page.document_id,
        page_number=page.page_number,
        text=page.text,
        method=page.method,
        state=page.state,
        char_count=page.char_count,
        extraction_version=page.extraction_version,
        quality=page.quality,
        has_image=page.image_key is not None,
    )
