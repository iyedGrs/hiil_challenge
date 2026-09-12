"""Document and page registries (spec/backend.md B4, B7, B8, B10).

Original bytes are preserved and addressed by a generated storage key; the
display name is sanitized and never used as a path. A document is detached by
clearing ``is_active`` and is never row-deleted, because a submitted version must
remain reachable through its snapshot (B10).

Page text is immutable once stored: publication validates quotes against it, so
rewriting it retroactively would invalidate published provenance (B7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import DocumentState, PageMethod, PageState
from app.models.base import (
    Base,
    JsonType,
    TimestampMixin,
    created_at_column,
    enum_type,
    id_column,
)


class Document(Base, TimestampMixin):
    """An uploaded original file scoped to one case (spec/backend.md B4).

    ``(case_id, sha256)`` is unique so an exact duplicate upload is detected
    within the authorized case only, and answers ``200 {duplicate: true}``
    without creating a second active file or a new revision (B9).
    """

    __tablename__ = "documents"

    id: Mapped[str] = id_column()
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[DocumentState] = mapped_column(
        enum_type(DocumentState), nullable=False, default=DocumentState.uploaded
    )
    #: False once detached from the working case. The row and bytes survive so a
    #: submitted snapshot stays accessible (spec/backend.md B10).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Contract error code explaining a rejected file; never a raw parser trace.
    rejection_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extraction_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    added_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    detached_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", order_by="Page.page_number"
    )

    __table_args__ = (
        UniqueConstraint("case_id", "sha256", name="uq_documents_case_id_sha256"),
        Index("ix_documents_case_id_is_active", "case_id", "is_active"),
    )


class Page(Base):
    """One 1-based page with immutable stored text (spec/backend.md B4, B7).

    ``quality`` holds OCR quality indicators, kept separate from citation-match
    status: a quote match proves correspondence to stored text, not scan
    authenticity or OCR correctness (B4).
    """

    __tablename__ = "pages"

    id: Mapped[str] = id_column()
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    method: Mapped[PageMethod] = mapped_column(enum_type(PageMethod), nullable=False)
    state: Mapped[PageState] = mapped_column(enum_type(PageState), nullable=False)
    quality: Mapped[dict[str, object]] = mapped_column(JsonType, nullable=False, default=dict)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Pointer to a rendered page image in private storage, when one exists.
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_column()

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_pages_document_id_page_number"),
        Index("ix_pages_case_id", "case_id"),
        Index("ix_pages_document_id_state", "document_id", "state"),
    )
