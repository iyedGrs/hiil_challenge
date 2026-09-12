import { useEffect, useState } from "react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { DocumentPage, DocumentRecord } from "../api/types";
import { Button } from "./Button";

const METHOD_LABEL: Record<NonNullable<DocumentPage["method"]>, string> = {
  embedded_text: "Texte intégral",
  ocr: "OCR",
};

interface DocumentPreviewProps {
  document: DocumentRecord;
  page: number;
  onPageChange: (page: number) => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; page: DocumentPage };

/**
 * Source-page preview (frontend.md FE-05 groundwork): renders one authorized
 * page at a time so a citation can deep-link to the exact page later (UI-05).
 */
export function DocumentPreview({ document, page, onPageChange }: DocumentPreviewProps) {
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
    <div className="rounded-md border border-border bg-surface p-4" dir="auto">
      <div className="flex items-center justify-between gap-4">
        <h3 className="truncate text-sm font-medium text-text" dir="auto">
          {document.filename}
        </h3>
        <a
          href={caseApi.getDocumentContentUrl(document.document_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-sm font-medium text-accent hover:underline"
        >
          Ouvrir l'original
        </a>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <Button
          variant="secondary"
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
        <Button variant="secondary" onClick={() => onPageChange(page + 1)} disabled={!canGoNext} aria-label="Page suivante">
          Suivant
        </Button>
      </div>

      <div className="mt-4">
        {state.status === "loading" && <div className="h-32 animate-pulse rounded-sm bg-surface-muted" />}

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
                className="whitespace-pre-wrap break-words rounded-sm border-l-2 border-border-strong bg-surface-muted p-3 text-sm text-text"
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
