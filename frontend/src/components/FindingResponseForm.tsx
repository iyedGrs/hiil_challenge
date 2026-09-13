import { useId, useState } from "react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CheckFinding, DocumentRecord, FindingAction, FindingResponse } from "../api/types";
import { Button } from "./Button";
import { FINDING_ACTION_LABEL } from "../lib/findingLabels";

interface FindingResponseFormProps {
  finding: CheckFinding;
  revision: number;
  /** Case's active documents — `add_evidence` can only attach documents already owned by the case. */
  activeDocuments: DocumentRecord[];
  onSubmitted: (revision: number, response: FindingResponse) => void;
  /** REVISION_CONFLICT: reload the whole case and ask the user to review again (frontend.md "Respond and reassess"). */
  onRevisionConflict: () => void;
}

function requiresExplanation(action: FindingAction): boolean {
  return action === "correct_claim" || action === "explain_unavailable" || action === "disagree";
}

/**
 * Response controls for one finding (frontend.md F4 "Respond and reassess",
 * FE-06). A saved response never marks the finding resolved — that is stated
 * explicitly in the UI, not implied by hiding the form.
 */
export function FindingResponseForm({
  finding,
  revision,
  activeDocuments,
  onSubmitted,
  onRevisionConflict,
}: FindingResponseFormProps) {
  const formId = useId();
  const [openAction, setOpenAction] = useState<FindingAction | null>(null);
  const [explanation, setExplanation] = useState("");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (finding.actions.length === 0) return null;

  function startAction(action: FindingAction): void {
    setOpenAction(action);
    setExplanation("");
    setDocumentIds([]);
    setError(null);
  }

  function cancel(): void {
    setOpenAction(null);
    setError(null);
  }

  function toggleDocument(documentId: string): void {
    setDocumentIds((prev) =>
      prev.includes(documentId) ? prev.filter((id) => id !== documentId) : [...prev, documentId],
    );
  }

  async function handleSubmit(): Promise<void> {
    if (!openAction) return;
    if (openAction === "add_evidence" && documentIds.length === 0) {
      setError("Sélectionnez au moins un document déjà présent dans ce dossier.");
      return;
    }
    if (requiresExplanation(openAction) && explanation.trim().length === 0) {
      setError("Une explication est nécessaire pour cette réponse.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const trimmedExplanation = explanation.trim();
      const result = await caseApi.respondToFinding(
        finding.finding_id,
        revision,
        openAction,
        trimmedExplanation.length > 0 ? trimmedExplanation : null,
        documentIds,
      );
      onSubmitted(result.revision, result.response);
      setOpenAction(null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        onRevisionConflict();
        return;
      }
      if (err instanceof ApiError) {
        setError(err.fieldErrors[0]?.message ?? err.message);
      } else {
        setError("Une erreur inattendue s'est produite. Réessayez.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-3 border-t border-border pt-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Répondre à ce constat">
        {finding.actions.map((action) => (
          <Button
            key={action}
            variant={openAction === action ? "primary" : "secondary"}
            onClick={() => (openAction === action ? cancel() : startAction(action))}
            aria-pressed={openAction === action}
          >
            {FINDING_ACTION_LABEL[action]}
          </Button>
        ))}
      </div>

      <p className="mt-2 text-xs text-text-subtle">
        La prochaine analyse déterminera l'état de cette vérification ; répondre ne clôt pas ce constat.
      </p>

      {openAction && (
        <div className="mt-3 flex flex-col gap-3 rounded-md border border-border bg-surface-muted p-3">
          {openAction === "add_evidence" && (
            <fieldset>
              <legend className="text-sm font-medium text-text">Documents à joindre</legend>
              {activeDocuments.length === 0 ? (
                <p className="mt-1 text-sm text-text-muted">Aucun document actif dans ce dossier.</p>
              ) : (
                <ul className="mt-2 flex flex-col gap-1.5">
                  {activeDocuments.map((doc) => {
                    const checkboxId = `${formId}-doc-${doc.document_id}`;
                    return (
                      <li key={doc.document_id} className="flex items-center gap-2">
                        <input
                          id={checkboxId}
                          type="checkbox"
                          checked={documentIds.includes(doc.document_id)}
                          onChange={() => toggleDocument(doc.document_id)}
                        />
                        <label htmlFor={checkboxId} className="text-sm text-text" dir="auto">
                          {doc.filename}
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </fieldset>
          )}

          <div>
            <label htmlFor={`${formId}-explanation`} className="text-sm font-medium text-text">
              Explication {requiresExplanation(openAction) && <span aria-hidden="true">*</span>}
            </label>
            <textarea
              id={`${formId}-explanation`}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              rows={3}
              dir="auto"
              aria-describedby={error ? `${formId}-error` : undefined}
              aria-invalid={error ? true : undefined}
              className="mt-1 w-full rounded-sm border border-border-strong bg-surface px-3 py-2 text-base text-text"
            />
          </div>

          {error && (
            <p id={`${formId}-error`} role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <Button onClick={() => void handleSubmit()} disabled={submitting}>
              {submitting ? "Envoi…" : "Envoyer la réponse"}
            </Button>
            <Button variant="secondary" onClick={cancel} disabled={submitting}>
              Annuler
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
