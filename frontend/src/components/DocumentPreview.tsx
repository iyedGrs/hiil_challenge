import { useEffect, useState } from "react";
import { ArrowSquareOut, CaretLeft, CaretRight, X } from "@phosphor-icons/react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { DocumentPage, DocumentRecord } from "../api/types";
import { Button, IconButton } from "./Button";

const METHOD_LABEL: Record<NonNullable<DocumentPage["method"]>, string> = {
  embedded_text: "Texte intégral",
  ocr: "OCR",
};

interface DocumentPreviewProps {
  document: DocumentRecord;
  page: number;
  onPageChange: (page: number) => void;
  /** Dismisses the viewer; omitted where the preview is the whole surface. */
  onClose?: () => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; page: DocumentPage };

/**
 * Source-page preview (frontend.md FE-05 groundwork): renders one authorized
 * page at a time so a citation can deep-link to the exact page later (UI-05).
 */
export function DocumentPreview({ document, page, onPageChange, onClose }: DocumentPreviewProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    caseApi
      .getDocumentPage(document.document_id, page)
      .then((result) => {
        if (!cancelled) setState({ status: "loaded", page: result });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Impossible de charger cette page.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [document.document_id, page]);

  const knownPages = document.pages;
  const canGoPrev = page > 1;
  const canGoNext = knownPages === null || page < knownPages;

  return (
    <div className="overflow-hidden rounded-md border border-border bg-surface shadow-raised" dir="auto">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
        <h3 className="min-w-0 flex-1 truncate text-md font-semibold text-text" dir="auto" title={document.filename}>
          {document.filename}
        </h3>
        <a
          href={caseApi.getDocumentContentUrl(document.document_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-accent hover:underline"
        >
          <ArrowSquareOut size={15} aria-hidden="true" />
          Ouvrir l'original
        </a>
        {onClose && <IconButton label="Fermer l'aperçu" icon={<X size={16} />} onClick={onClose} />}
      </div>

      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <Button
          variant="secondary"
          size="sm"
          icon={<CaretLeft size={14} weight="bold" />}
          onClick={() => onPageChange(page - 1)}
          disabled={!canGoPrev}
          aria-label="Page précédente"
        >
          Précédent
        </Button>
        <p className="tabular text-sm text-text-muted">
          Page {page}
          {knownPages !== null ? ` / ${knownPages}` : ""}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={!canGoNext}
          aria-label="Page suivante"
        >
          Suivant
          <CaretRight size={14} weight="bold" aria-hidden="true" />
        </Button>
      </div>

      <div className="px-4 pb-4">
        {state.status === "loading" && <div className="skeleton h-40 rounded-sm" />}

        {state.status === "error" && (
          <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            {state.message}
          </p>
        )}

        {state.status === "loaded" && (
          <div className="flex flex-col gap-3">
            {state.page.image_url && (
              <img
                src={state.page.image_url}
                alt={`Aperçu de la page ${page} de ${document.filename}`}
                className="max-h-96 rounded-sm border border-border object-contain"
              />
            )}

            {(state.page.method || state.page.quality) && (
              <p className="text-xs text-text-muted">
                {state.page.method && <>Méthode : {METHOD_LABEL[state.page.method]}</>}
                {state.page.method && state.page.quality && " · "}
                {state.page.quality && <>Qualité : {state.page.quality}</>}
              </p>
            )}

            {state.page.source_text ? (
              <pre
                dir="auto"
                style={{ unicodeBidi: "plaintext" }}
                className="font-sans whitespace-pre-wrap break-words rounded-sm border border-border bg-surface-muted p-3 text-sm leading-relaxed text-text"
              >
                {state.page.source_text}
              </pre>
            ) : (
              <p className="text-sm text-text-subtle">Aucun texte source disponible pour cette page.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
