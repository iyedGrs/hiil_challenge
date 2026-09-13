import { useRef, useState, type DragEvent } from "react";
import {
  CheckCircle,
  CopySimple,
  FolderOpen,
  Prohibit,
  UploadSimple,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { AppConfig, DocumentRecord } from "../api/types";
import { Button, IconButton } from "./Button";
import { DocumentPreview } from "./DocumentPreview";
import { DocumentTile } from "./DocumentTile";
import { useToast } from "./Toast";
import { formatMiB } from "../lib/documentState";

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

/** Upload workspace: drop zone, quota readout, document grid and page viewer (frontend.md F4). */
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
  const { notify } = useToast();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
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
    let addedCount = 0;

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
          addedCount += 1;
          updateQueueItem(i, { status: "added" });
        }
        onUpdate(currentRevision, currentDocuments);
      } catch (err) {
        if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
          updateQueueItem(i, { status: "rejected", message: "Le dossier a changé, rechargement en cours." });
          for (let j = i + 1; j < files.length; j += 1) {
            if (items[j].status === "pending") updateQueueItem(j, { status: "stopped", message: "Non envoyé, dossier rechargé." });
          }
          onReload();
          return;
        }
        const message = err instanceof ApiError ? err.message : "Erreur inattendue lors de l'envoi.";
        updateQueueItem(i, { status: "rejected", message });
      }
    }

    if (addedCount > 0) {
      notify("success", addedCount === 1 ? "1 pièce ajoutée au dossier." : `${addedCount} pièces ajoutées au dossier.`);
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

  function handleDragOver(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>): void {
    if (event.currentTarget.contains(event.relatedTarget as Node)) return;
    setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    handleFilesSelected(event.dataTransfer?.files ?? null);
  }

  async function handleRemove(doc: DocumentRecord): Promise<void> {
    setRowError((prev) => ({ ...prev, [doc.document_id]: "" }));
    try {
      const result = await caseApi.deleteDocument(caseId, doc.document_id, revision);
      onUpdate(
        result.revision,
        documents.map((d) => (d.document_id === doc.document_id ? { ...d, active: false } : d)),
      );
      if (selectedDocumentId === doc.document_id) onSelectDocument(null);
      notify("info", `${doc.filename} a été retiré du dossier.`);
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
        notify("warning", "Ce fichier est déjà présent dans le dossier.");
      } else {
        const deleteResult = await caseApi.deleteDocument(caseId, oldDocumentId, nextRevision);
        nextRevision = deleteResult.revision;
        nextDocuments = nextDocuments.map((d) => (d.document_id === oldDocumentId ? { ...d, active: false } : d));
        notify("success", "Pièce remplacée.");
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
  const atFileLimit = activeDocuments.length >= limits.max_active_files;

  return (
    <div className="flex flex-col gap-5">
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

      <div
        onDragEnter={handleDragOver}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`rounded-md border-2 border-dashed p-6 text-center transition-colors ${
          dragging ? "border-accent bg-accent-soft" : "border-border-strong bg-surface"
        }`}
      >
        <span
          aria-hidden="true"
          className={`mx-auto flex size-11 items-center justify-center rounded-full transition-colors ${
            dragging ? "bg-surface text-accent" : "bg-surface-muted text-text-subtle"
          }`}
        >
          <UploadSimple size={22} />
        </span>
        <p className="mt-3 text-sm font-medium text-text">
          {dragging ? "Déposez pour ajouter au dossier" : "Glissez vos pièces ici"}
        </p>
        <div className="mt-3 flex justify-center">
          <Button icon={<FolderOpen size={15} />} onClick={handleUploadClick} disabled={atFileLimit}>
            Parcourir mes fichiers
          </Button>
        </div>
        <p className="mt-2 text-xs text-text-subtle">
          PDF, JPEG ou PNG · <span className="tabular">{formatMiB(limits.max_file_bytes)}</span> maximum par fichier
        </p>
      </div>

      <dl className="grid grid-cols-3 gap-4 rounded-md border border-border bg-surface-muted px-4 py-3">
        <div>
          <dt className="text-xs text-text-subtle">Fichiers actifs</dt>
          <dd className={`tabular text-sm font-medium ${atFileLimit ? "text-warning" : "text-text"}`}>
            {activeDocuments.length} / {limits.max_active_files}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-subtle">Pages totales</dt>
          <dd className={`tabular text-sm font-medium ${usedPages >= limits.max_total_pages ? "text-warning" : "text-text"}`}>
            {usedPages} / {limits.max_total_pages}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-subtle">Taille utilisée</dt>
          <dd className="tabular text-sm font-medium text-text">
            {formatMiB(usedBytes)} / {formatMiB(limits.max_case_bytes)}
          </dd>
        </div>
      </dl>

      {queue.length > 0 && (
        <div className="rounded-md border border-border bg-surface p-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-xs font-medium text-text-muted">Envoi en cours</h3>
            <IconButton label="Masquer le suivi d'envoi" icon={<X size={14} />} onClick={() => setQueue([])} />
          </div>
          <ul className="mt-1.5 flex flex-col divide-y divide-border">
            {queue.map((item) => (
              <li key={item.key} className="flex items-start gap-2 py-1.5 text-sm">
                <span aria-hidden="true" className="mt-0.5 shrink-0">
                  {QUEUE_STATUS_ICON[item.status]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-text" dir="auto">
                    {item.filename}
                  </span>
                  <span className="block text-xs text-text-muted">
                    {QUEUE_STATUS_LABEL[item.status]}
                    {item.message ? ` · ${item.message}` : ""}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {activeDocuments.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-text-muted">
          Aucune pièce pour l'instant. Ajoutez la facture, la preuve de livraison et tout reçu de paiement.
        </p>
      ) : (
        <ul
          aria-label="Pièces du dossier"
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
        >
          {activeDocuments.map((doc) => (
            <DocumentTile
              key={doc.document_id}
              document={doc}
              selected={doc.document_id === selectedDocumentId}
              rowError={rowError[doc.document_id] || undefined}
              confirmingRemove={confirmRemoveId === doc.document_id}
              highlighted={highlightId === doc.document_id}
              onOpen={() => onSelectDocument(doc.document_id)}
              onReplace={() => handleReplaceClick(doc.document_id)}
              onRequestRemove={() => setConfirmRemoveId(doc.document_id)}
              onConfirmRemove={() => void handleRemove(doc)}
              onCancelRemove={() => setConfirmRemoveId(null)}
            />
          ))}
        </ul>
      )}

      {selectedDocument && (
        <div className="animate-enter-up">
          <DocumentPreview
            document={selectedDocument}
            page={selectedPage}
            onPageChange={onSelectPage}
            onClose={() => onSelectDocument(null)}
          />
        </div>
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

const QUEUE_STATUS_ICON: Record<QueueItemStatus, React.ReactNode> = {
  pending: <span className="block size-3.5 rounded-full border border-border-strong" />,
  uploading: <span className="block size-3.5 rounded-full bg-accent animate-breathe" />,
  added: <CheckCircle size={15} weight="fill" className="text-success" />,
  duplicate: <CopySimple size={15} className="text-warning" />,
  rejected: <WarningCircle size={15} weight="fill" className="text-danger" />,
  stopped: <Prohibit size={15} className="text-muted" />,
};
