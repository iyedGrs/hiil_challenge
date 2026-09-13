import { useRef, useState } from "react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { AppConfig, DocumentRecord } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { DocumentPreview } from "./DocumentPreview";
import { DOCUMENT_STATE_LABEL, DOCUMENT_STATE_TONE, formatMiB, formatUploadedAt } from "../lib/documentState";

const ACCEPTED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"];
const ACCEPT_ATTR = ACCEPTED_MIME_TYPES.join(",");

type QueueItemStatus = "pending" | "uploading" | "added" | "duplicate" | "rejected" | "stopped";

interface QueueItem {
  key: string;
  filename: string;
  status: QueueItemStatus;
  message?: string;
}

interface DocumentWorkspaceProps {
  caseId: string;
  revision: number;
  documents: DocumentRecord[];
  config: AppConfig;
  /** Applies a revision/documents update the parent should reflect immediately (no full reload). */
  onUpdate: (revision: number, documents: DocumentRecord[]) => void;
  /** Full case reload — used after REVISION_CONFLICT, per frontend.md/B9. */
  onReload: () => void;
  selectedDocumentId: string | null;
  selectedPage: number;
  onSelectDocument: (documentId: string | null) => void;
  onSelectPage: (page: number) => void;
}

function precheckFile(
  file: File,
  limits: AppConfig["limits"],
  plannedCount: number,
  plannedBytes: number,
): { ok: true } | { ok: false; message: string } {
  if (!ACCEPTED_MIME_TYPES.includes(file.type)) {
    return { ok: false, message: "Format non pris en charge (PDF, JPEG ou PNG uniquement)." };
  }
  if (file.size > limits.max_file_bytes) {
    return { ok: false, message: `Fichier trop volumineux (maximum ${formatMiB(limits.max_file_bytes)}).` };
  }
  if (plannedCount + 1 > limits.max_active_files) {
    return { ok: false, message: "Nombre maximal de fichiers atteint pour ce dossier." };
  }
  if (plannedBytes + file.size > limits.max_case_bytes) {
    return { ok: false, message: "Taille totale du dossier dépassée." };
  }
  return { ok: true };
}

/** Upload list, per-file limits feedback and remove/replace controls (frontend.md F4 "Document workspace"). */
export function DocumentWorkspace({
  caseId,
  revision,
  documents,
  config,
  onUpdate,
  onReload,
  selectedDocumentId,
  selectedPage,
  onSelectDocument,
  onSelectPage,
}: DocumentWorkspaceProps) {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const [replacingId, setReplacingId] = useState<string | null>(null);

  const activeDocuments = documents.filter((d) => d.active);
  const usedBytes = activeDocuments.reduce((sum, d) => sum + d.size_bytes, 0);
  const usedPages = activeDocuments.reduce((sum, d) => sum + (d.pages ?? 0), 0);
  const { limits } = config;

  function updateQueueItem(index: number, patch: Partial<QueueItem>): void {
    setQueue((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function scrollToDocument(documentId: string): void {
    setHighlightId(documentId);
    document.getElementById(`document-row-${documentId}`)?.scrollIntoView?.({ block: "nearest" });
    window.setTimeout(() => setHighlightId((current) => (current === documentId ? null : current)), 2000);
  }

  async function runUpload(files: File[]): Promise<void> {
    let plannedCount = activeDocuments.length;
    let plannedBytes = usedBytes;
    const items: QueueItem[] = files.map((file) => {
      const check = precheckFile(file, limits, plannedCount, plannedBytes);
      if (check.ok) {
        plannedCount += 1;
        plannedBytes += file.size;
        return { key: `${file.name}-${file.size}-${plannedCount}`, filename: file.name, status: "pending" };
      }
      return { key: `${file.name}-${file.size}-${plannedCount}`, filename: file.name, status: "rejected", message: check.message };
    });
    setQueue(items);

    let currentRevision = revision;
    let currentDocuments = documents;

    for (let i = 0; i < files.length; i += 1) {
      if (items[i].status !== "pending") continue;
      updateQueueItem(i, { status: "uploading" });
      try {
        const result = await caseApi.uploadDocument(caseId, currentRevision, files[i]);
        currentRevision = result.revision;
        if (result.duplicate) {
          updateQueueItem(i, { status: "duplicate", message: "Ce fichier est déjà présent." });
          scrollToDocument(result.document.document_id);
        } else {
          currentDocuments = [...currentDocuments, result.document];
          updateQueueItem(i, { status: "added" });
        }
        onUpdate(currentRevision, currentDocuments);
      } catch (err) {
        if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
          updateQueueItem(i, { status: "rejected", message: "Le dossier a changé. Rechargement en cours…" });
          for (let j = i + 1; j < files.length; j += 1) {
            if (items[j].status === "pending") updateQueueItem(j, { status: "stopped", message: "Non envoyé — dossier rechargé." });
          }
          onReload();
          return;
        }
        const message = err instanceof ApiError ? err.message : "Erreur inattendue lors de l'envoi.";
        updateQueueItem(i, { status: "rejected", message });
      }
    }
  }

  function handleUploadClick(): void {
    uploadInputRef.current?.click();
  }

  function handleFilesSelected(files: FileList | null): void {
    if (!files || files.length === 0) return;
    void runUpload([...files]);
    if (uploadInputRef.current) uploadInputRef.current.value = "";
  }

  async function handleRemove(doc: DocumentRecord): Promise<void> {
    setRowError((prev) => ({ ...prev, [doc.document_id]: "" }));
    try {
      const result = await caseApi.deleteDocument(caseId, doc.document_id, revision);
      onUpdate(
        result.revision,
        documents.map((d) => (d.document_id === doc.document_id ? { ...d, active: false } : d)),
      );
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        onReload();
        return;
      }
      const message = err instanceof ApiError ? err.message : "Le retrait a échoué.";
      setRowError((prev) => ({ ...prev, [doc.document_id]: message }));
    } finally {
      setConfirmRemoveId(null);
    }
  }

  function handleReplaceClick(documentId: string): void {
    setReplacingId(documentId);
    replaceInputRef.current?.click();
  }

  async function handleReplaceFileSelected(files: FileList | null): Promise<void> {
    const oldDocumentId = replacingId;
    setReplacingId(null);
    if (replaceInputRef.current) replaceInputRef.current.value = "";
    if (!files || files.length === 0 || !oldDocumentId) return;
    const file = files[0];

    setRowError((prev) => ({ ...prev, [oldDocumentId]: "" }));
    try {
      const uploadResult = await caseApi.uploadDocument(caseId, revision, file);
      let nextDocuments = uploadResult.duplicate ? documents : [...documents, uploadResult.document];
      let nextRevision = uploadResult.revision;
      if (uploadResult.duplicate) {
        scrollToDocument(uploadResult.document.document_id);
      } else {
        const deleteResult = await caseApi.deleteDocument(caseId, oldDocumentId, nextRevision);
        nextRevision = deleteResult.revision;
        nextDocuments = nextDocuments.map((d) => (d.document_id === oldDocumentId ? { ...d, active: false } : d));
      }
      onUpdate(nextRevision, nextDocuments);
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        onReload();
        return;
      }
      const message = err instanceof ApiError ? err.message : "Le remplacement a échoué.";
      setRowError((prev) => ({ ...prev, [oldDocumentId]: message }));
    }
  }

  const selectedDocument = activeDocuments.find((d) => d.document_id === selectedDocumentId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-md border border-border bg-surface-muted p-4">
        <h3 className="text-sm font-medium text-text">Limites du dossier</h3>
        <dl className="mt-2 grid grid-cols-1 gap-2 text-sm text-text-muted sm:grid-cols-3">
          <div>
            <dt className="text-xs text-text-subtle">Fichiers actifs</dt>
            <dd className="tabular">
              {activeDocuments.length} / {limits.max_active_files}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Pages totales</dt>
            <dd className="tabular">
              {usedPages} / {limits.max_total_pages}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Taille utilisée</dt>
            <dd className="tabular">
              {formatMiB(usedBytes)} / {formatMiB(limits.max_case_bytes)}
            </dd>
          </div>
        </dl>
      </div>

      <div>
        <input
          ref={uploadInputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTR}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => handleFilesSelected(e.target.files)}
        />
        <input
          ref={replaceInputRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => void handleReplaceFileSelected(e.target.files)}
        />
        <Button onClick={handleUploadClick}>Ajouter des documents</Button>
        <p className="mt-1 text-xs text-text-subtle">PDF, JPEG ou PNG. Chaque fichier est envoyé un par un.</p>

        {queue.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1">
            {queue.map((item) => (
              <li key={item.key} className="flex items-center gap-2 text-sm">
                <span className="truncate text-text" dir="auto">
                  {item.filename}
                </span>
                <span className="text-text-muted">— {QUEUE_STATUS_LABEL[item.status]}</span>
                {item.message && <span className="text-text-subtle">({item.message})</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <ul className="flex flex-col gap-2">
        {activeDocuments.length === 0 && (
          <li className="rounded-md border border-dashed border-border p-4 text-sm text-text-muted">
            Aucun document pour l'instant — ajoutez-en un ci-dessus.
          </li>
        )}
        {activeDocuments.map((doc) => (
          <li
            key={doc.document_id}
            id={`document-row-${doc.document_id}`}
            className={`rounded-md border p-3 transition-colors ${
              highlightId === doc.document_id ? "border-accent bg-accent-soft" : "border-border bg-surface"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => onSelectDocument(doc.document_id)}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block truncate text-sm font-medium text-accent hover:underline" dir="auto">
                  {doc.filename}
                </span>
                <span className="text-xs text-text-muted">
                  {doc.document_type ?? "Type non déterminé"} · {doc.pages ?? "?"} page(s) ·{" "}
                  {formatUploadedAt(doc.uploaded_at)} · {formatMiB(doc.size_bytes)}
                </span>
              </button>
              <Badge tone={DOCUMENT_STATE_TONE[doc.state]}>{DOCUMENT_STATE_LABEL[doc.state]}</Badge>
            </div>

            {doc.error && (
              <p role="alert" className="mt-2 rounded-sm bg-danger-bg px-2.5 py-1.5 text-sm text-danger">
                {doc.error}
              </p>
            )}
            {rowError[doc.document_id] && (
              <p role="alert" className="mt-2 rounded-sm bg-danger-bg px-2.5 py-1.5 text-sm text-danger">
                {rowError[doc.document_id]}
              </p>
            )}

            <div className="mt-2 flex items-center gap-2">
              <Button variant="secondary" onClick={() => handleReplaceClick(doc.document_id)}>
                Remplacer
              </Button>
              {confirmRemoveId === doc.document_id ? (
                <>
                  <span className="text-sm text-text-muted">Confirmer le retrait ?</span>
                  <Button variant="secondary" onClick={() => void handleRemove(doc)}>
                    Confirmer
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirmRemoveId(null)}>
                    Annuler
                  </Button>
                </>
              ) : (
                <Button variant="secondary" onClick={() => setConfirmRemoveId(doc.document_id)}>
                  Retirer
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {selectedDocument && (
        <DocumentPreview document={selectedDocument} page={selectedPage} onPageChange={onSelectPage} />
      )}
    </div>
  );
}

const QUEUE_STATUS_LABEL: Record<QueueItemStatus, string> = {
  pending: "En attente",
  uploading: "Envoi…",
  added: "Ajouté",
  duplicate: "Doublon",
  rejected: "Refusé",
  stopped: "Arrêté",
};
