import { useEffect, useState } from "react";
import {
  ArrowsClockwise,
  Eye,
  FileImage,
  FilePdf,
  FileX,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { caseApi } from "../api";
import type { DocumentRecord } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { Menu } from "./Menu";
import { DOCUMENT_STATE_LABEL, DOCUMENT_STATE_TONE, formatMiB, formatUploadedAt } from "../lib/documentState";

type Thumbnail =
  | { kind: "loading" }
  | { kind: "image"; url: string }
  | { kind: "text"; text: string }
  | { kind: "none" };

/** Enough of page 1 to recognise the document; the sheet clips whatever overflows. */
const PREVIEW_CHARS = 700;

function isPreviewable(doc: DocumentRecord): boolean {
  return doc.state === "ready" || doc.state === "partial";
}

function fallbackIcon(doc: DocumentRecord) {
  if (doc.state === "unreadable" || doc.state === "rejected") return <FileX size={30} />;
  if (/\.(png|jpe?g)$/i.test(doc.filename)) return <FileImage size={30} />;
  return <FilePdf size={30} />;
}

interface DocumentTileProps {
  document: DocumentRecord;
  selected: boolean;
  rowError?: string;
  confirmingRemove: boolean;
  highlighted: boolean;
  onOpen: () => void;
  onReplace: () => void;
  onRequestRemove: () => void;
  onConfirmRemove: () => void;
  onCancelRemove: () => void;
}

/**
 * One document as a card that shows what is actually inside it. A list of bare
 * filenames forced the user to open every file to know what it was; the tile
 * renders page 1 (rendered image when the backend has one, otherwise the
 * extracted text set as a miniature sheet) so the dossier can be recognised at
 * a glance. All three per-file controls collapse into one overflow menu.
 */
export function DocumentTile({
  document: doc,
  selected,
  rowError,
  confirmingRemove,
  highlighted,
  onOpen,
  onReplace,
  onRequestRemove,
  onConfirmRemove,
  onCancelRemove,
}: DocumentTileProps) {
  const [thumbnail, setThumbnail] = useState<Thumbnail>({ kind: "loading" });
  const documentId = doc.document_id;
  const previewable = isPreviewable(doc);

  useEffect(() => {
    if (!previewable) {
      setThumbnail({ kind: "none" });
      return;
    }
    let cancelled = false;
    setThumbnail({ kind: "loading" });
    // Promise.resolve(): the page route is optional in some data modes and must
    // never take the tile down when it is unavailable.
    Promise.resolve(caseApi.getDocumentPage(documentId, 1))
      .then((page) => {
        if (cancelled) return;
        if (page?.image_url) setThumbnail({ kind: "image", url: page.image_url });
        else if (page?.source_text) setThumbnail({ kind: "text", text: page.source_text.slice(0, PREVIEW_CHARS) });
        else setThumbnail({ kind: "none" });
      })
      .catch(() => {
        if (!cancelled) setThumbnail({ kind: "none" });
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, previewable]);

  return (
    <li
      id={`document-row-${doc.document_id}`}
      data-scroll-target=""
      className={`flex flex-col overflow-hidden rounded-md border bg-surface transition-[border-color,box-shadow] hover:shadow-lifted ${
        selected ? "border-accent shadow-lifted" : "border-border shadow-raised hover:border-border-strong"
      } ${highlighted ? "animate-flash" : ""}`}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-current={selected ? "true" : undefined}
        className="group/tile flex flex-1 flex-col text-start"
      >
        <span className="relative block aspect-[4/3] overflow-hidden border-b border-border bg-surface-muted">
          {thumbnail.kind === "loading" && <span className="skeleton absolute inset-0 block" />}

          {thumbnail.kind === "image" && (
            <img
              src={thumbnail.url}
              alt={`Première page de ${doc.filename}`}
              loading="lazy"
              className="size-full object-cover object-top"
            />
          )}

          {thumbnail.kind === "text" && (
            <span
              aria-hidden="true"
              dir="auto"
              className="absolute inset-x-3 top-3 bottom-0 block overflow-hidden rounded-t-sm border border-border border-b-0 bg-surface px-2.5 py-2 text-[7px] leading-[1.45] whitespace-pre-wrap text-text-muted"
              style={{ unicodeBidi: "plaintext" }}
            >
              {thumbnail.text}
            </span>
          )}

          {thumbnail.kind === "none" && (
            <span className="absolute inset-0 flex items-center justify-center text-text-subtle">
              {fallbackIcon(doc)}
            </span>
          )}

          {/* Reveals the affordance without covering the preview with a label. */}
          <span className="absolute inset-0 flex items-end justify-end p-2 opacity-0 transition-opacity group-hover/tile:opacity-100 group-focus-visible/tile:opacity-100">
            <span className="inline-flex items-center gap-1 rounded-full bg-surface/95 px-2 py-1 text-xs font-medium text-accent shadow-raised">
              <Eye size={13} aria-hidden="true" />
              Ouvrir
            </span>
          </span>
        </span>

        <span className="block p-3">
          <span className="block truncate text-sm font-medium text-text" dir="auto" title={doc.filename}>
            {doc.filename}
          </span>
          <span className="mt-1 block text-xs text-text-muted">
            {doc.document_type ?? "Type non déterminé"} · <span className="tabular">{doc.pages ?? "?"}</span> page(s) ·{" "}
            <span className="tabular">{formatMiB(doc.size_bytes)}</span>
          </span>
          <span className="tabular mt-0.5 block text-xs text-text-subtle">{formatUploadedAt(doc.uploaded_at)}</span>
        </span>
      </button>

      {doc.error && (
        <p role="alert" className="flex items-start gap-1.5 border-t border-border bg-danger-bg px-3 py-2 text-xs text-danger">
          <WarningCircle size={14} weight="fill" aria-hidden="true" className="mt-px shrink-0" />
          {doc.error}
        </p>
      )}
      {rowError && (
        <p role="alert" className="flex items-start gap-1.5 border-t border-border bg-danger-bg px-3 py-2 text-xs text-danger">
          <WarningCircle size={14} weight="fill" aria-hidden="true" className="mt-px shrink-0" />
          {rowError}
        </p>
      )}

      {confirmingRemove ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border bg-warning-bg px-3 py-2">
          <p className="text-xs font-medium text-warning">Retirer cette pièce du dossier ?</p>
          <div className="flex gap-1.5">
            <Button variant="secondary" size="sm" onClick={onCancelRemove}>
              Annuler
            </Button>
            <Button variant="danger" size="sm" onClick={onConfirmRemove}>
              Retirer
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2">
          <Badge tone={DOCUMENT_STATE_TONE[doc.state]}>{DOCUMENT_STATE_LABEL[doc.state]}</Badge>
          <Menu
            label={`Actions pour ${doc.filename}`}
            actions={[
              { id: "open", label: "Ouvrir", icon: <Eye size={15} />, onSelect: onOpen },
              { id: "replace", label: "Remplacer", icon: <ArrowsClockwise size={15} />, onSelect: onReplace },
              { id: "remove", label: "Retirer", icon: <Trash size={15} />, tone: "danger", onSelect: onRequestRemove },
            ]}
          />
        </div>
      )}
    </li>
  );
}
