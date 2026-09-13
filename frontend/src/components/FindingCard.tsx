import type { CheckFinding, DocumentRecord, FindingResponse } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { FindingResponseForm } from "./FindingResponseForm";
import {
  CHECK_RESULT_LABEL,
  CHECK_RESULT_TONE,
  FINDING_DELTA_LABEL,
  FINDING_DELTA_TONE,
  FINDING_STATUS_LABEL,
  FINDING_STATUS_TONE,
} from "../lib/findingLabels";

const BASIS_LABEL: Record<CheckFinding["basis"], string> = {
  checklist: "Checklist",
  contract: "Contrat",
  claim: "Réclamation",
  deterministic: "Vérification déterministe (fichier/montant)",
};

interface FindingCardProps {
  finding: CheckFinding;
  revision: number;
  /** Every document ever attached to the case (active or not) — used only to resolve filenames for display. */
  documents: DocumentRecord[];
  existingResponse: FindingResponse | null;
  onRespond?: (revision: number, response: FindingResponse) => void;
  onRevisionConflict?: () => void;
  onOpenDocumentPage: (documentId: string, page: number) => void;
  /** Reviewer back office (UI-08): hides the response form — a reviewer never edits evidence or rewrites findings. */
  readOnly?: boolean;
}

function documentLabel(documents: DocumentRecord[], documentId: string): string {
  return documents.find((d) => d.document_id === documentId)?.filename ?? documentId;
}

/**
 * One validated finding (frontend.md F4 "Analysis and findings"). Keyed by
 * the server-owned `finding_id` by the caller — never by title or array
 * position (FE-06).
 */
export function FindingCard({
  finding,
  revision,
  documents,
  existingResponse,
  onRespond,
  onRevisionConflict,
  onOpenDocumentPage,
  readOnly,
}: FindingCardProps) {
  const activeDocuments = documents.filter((d) => d.active);
  const unreviewableDocuments = documents.filter(
    (d) => (d.state === "unreadable" || d.state === "rejected") && !finding.reviewed_document_ids.includes(d.document_id),
  );

  return (
    <li className="rounded-md border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-text" dir="auto">
            {finding.subject_label}
          </h3>
          <p className="text-xs text-text-subtle">
            {finding.check_id} · {finding.subject_id} · <span className="tabular">{finding.finding_id}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={CHECK_RESULT_TONE[finding.result]}>{CHECK_RESULT_LABEL[finding.result]}</Badge>
          {finding.finding_status && (
            <Badge tone={FINDING_STATUS_TONE[finding.finding_status]}>{FINDING_STATUS_LABEL[finding.finding_status]}</Badge>
          )}
          {finding.delta && <Badge tone={FINDING_DELTA_TONE[finding.delta]}>{FINDING_DELTA_LABEL[finding.delta]}</Badge>}
        </div>
      </div>

      <p className="mt-2 text-xs text-text-subtle">Base : {BASIS_LABEL[finding.basis]}</p>
      <p className="mt-1 text-sm text-text" dir="auto">
        {finding.message}
      </p>

      <div className="mt-3 text-xs text-text-muted">
        <p>
          Documents examinés :{" "}
          {finding.reviewed_document_ids.length > 0
            ? finding.reviewed_document_ids.map((id) => documentLabel(documents, id)).join(", ")
            : "aucun"}
        </p>
        {unreviewableDocuments.length > 0 && (
          <p className="mt-1">
            Documents non examinables : {unreviewableDocuments.map((d) => d.filename).join(", ")}
          </p>
        )}
      </div>

      {finding.evidence_refs.length > 0 && (
        <div className="mt-3">
          <h4 className="text-xs font-medium text-text-muted">Passages cités</h4>
          <ul className="mt-1.5 flex flex-col gap-2">
            {finding.evidence_refs.map((ref) => (
              <li
                key={ref.fact_id}
                className="border-l-2 border-border-strong bg-surface-muted px-3 py-2 text-sm text-text"
              >
                <p dir="auto" style={{ unicodeBidi: "plaintext" }}>
                  {ref.source_text}
                </p>
                <Button
                  variant="secondary"
                  className="mt-1.5"
                  onClick={() => onOpenDocumentPage(ref.document_id, ref.page)}
                >
                  Voir {documentLabel(documents, ref.document_id)}, page {ref.page}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {finding.legal_reference_ids.length > 0 && (
        <p className="mt-3 text-xs text-text-subtle">
          Références légales : <span className="tabular">{finding.legal_reference_ids.join(", ")}</span>
        </p>
      )}

      {existingResponse && (
        <div className="mt-3 rounded-sm bg-info-bg px-2.5 py-1.5 text-sm text-info">
          <p className="font-medium">Réponse précédente enregistrée</p>
          {existingResponse.explanation && (
            <p className="mt-0.5" dir="auto">
              {existingResponse.explanation}
            </p>
          )}
          {existingResponse.document_ids.length > 0 && (
            <p className="mt-0.5">
              Pièces jointes : {existingResponse.document_ids.map((id) => documentLabel(documents, id)).join(", ")}
            </p>
          )}
        </div>
      )}

      {!readOnly && onRespond && onRevisionConflict && (
        <FindingResponseForm
          finding={finding}
          revision={revision}
          activeDocuments={activeDocuments}
          onSubmitted={onRespond}
          onRevisionConflict={onRevisionConflict}
        />
      )}
    </li>
  );
}
