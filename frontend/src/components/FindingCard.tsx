import { useId, useState } from "react";
import { CaretDown, ChatText, Eye, WarningCircle } from "@phosphor-icons/react";
import type { CheckFinding, DocumentRecord, FindingResponse } from "../api/types";
import { Button } from "./Button";
import { StatusLabel } from "./Badge";
import { FindingResponseForm } from "./FindingResponseForm";
import {
  CHECK_RESULT_ICON,
  CHECK_RESULT_LABEL,
  CHECK_RESULT_TONE,
  FINDING_DELTA_LABEL,
  FINDING_STATUS_LABEL,
} from "../lib/findingLabels";

const BASIS_LABEL: Record<CheckFinding["basis"], string> = {
  checklist: "Checklist",
  evidence_guidance: "Pièces / contrat / réclamation",
  reconciliation: "Vérification déterministe (fichier/montant)",
};

/** Severity reads as a tinted header band and a filled glyph, never a colored edge rail. */
const HEADER_TINT: Record<CheckFinding["result"], string> = {
  contradicted: "bg-danger-bg hover:brightness-[0.97]",
  unassessable: "bg-warning-bg hover:brightness-[0.97]",
  satisfied: "bg-surface hover:bg-surface-muted",
  not_applicable: "bg-surface hover:bg-surface-muted",
};

const CARD_BORDER: Record<CheckFinding["result"], string> = {
  contradicted: "border-danger/35",
  unassessable: "border-warning/35",
  satisfied: "border-border",
  not_applicable: "border-border",
};

/** Filled for an outstanding issue, tinted for a settled one. */
const GLYPH_CLASSES: Record<CheckFinding["result"], string> = {
  contradicted: "bg-danger text-white",
  unassessable: "bg-warning text-white",
  satisfied: "bg-success-bg text-success",
  not_applicable: "bg-muted-bg text-muted",
};

interface FindingCardProps {
  finding: CheckFinding;
  revision: number;
  /** Every document ever attached to the case (active or not), used only to resolve filenames. */
  documents: DocumentRecord[];
  existingResponse: FindingResponse | null;
  onRespond?: (revision: number, response: FindingResponse) => void;
  onRevisionConflict?: () => void;
  onOpenDocumentPage: (documentId: string, page: number) => void;
  /** Reviewer back office (UI-08): hides the response form. A reviewer never rewrites findings. */
  readOnly?: boolean;
  /** Set for ~2s after a verdict label jumped here, so the target of the jump is unmistakable. */
  flash?: boolean;
}

function documentLabel(documents: DocumentRecord[], documentId: string): string {
  return documents.find((d) => d.document_id === documentId)?.filename ?? documentId;
}

/**
 * One validated finding (frontend.md F4 "Analysis and findings"), keyed by the
 * server-owned `finding_id` by the caller, never by title or array position
 * (FE-06).
 *
 * The card is a disclosure. Outstanding issues open themselves because they are
 * the work; settled checks collapse to a single scannable row, so a dossier
 * with one problem among six checks reads as one problem rather than six walls
 * of text.
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
  flash,
}: FindingCardProps) {
  const bodyId = useId();
  const isIssue = finding.result === "contradicted" || finding.result === "unassessable";
  const [toggled, setToggled] = useState<boolean | null>(null);

  /*
   * Outstanding issues open themselves; settled checks start collapsed. A jump
   * from a verdict label pins the card open for the duration of the flash, so
   * the jump can never land on a row the user then has to expand. Derived
   * rather than synced through an effect.
   */
  const open = flash ? true : (toggled ?? isIssue);

  const activeDocuments = documents.filter((d) => d.active);
  const unreviewableDocuments = documents.filter(
    (d) => (d.state === "unreadable" || d.state === "rejected") && !finding.reviewed_document_ids.includes(d.document_id),
  );

  const ResultIcon = CHECK_RESULT_ICON[finding.result];
  const tone = CHECK_RESULT_TONE[finding.result];
  /** Only the deltas that ask for attention earn a place in the collapsed row. */
  const headlineDelta = finding.delta === "new" || finding.delta === "reopened" ? finding.delta : null;

  return (
    <li
      id={`finding-${finding.finding_id}`}
      data-scroll-target=""
      className={`overflow-hidden rounded-md border bg-surface shadow-raised ${CARD_BORDER[finding.result]} ${
        flash ? "animate-flash" : ""
      }`}
    >
      <h3>
        <button
          type="button"
          onClick={() => setToggled(!open)}
          aria-expanded={open}
          aria-controls={bodyId}
          className={`flex w-full items-center gap-3 px-4 py-3.5 text-start transition-[background-color,filter] ${HEADER_TINT[finding.result]}`}
        >
          <span
            aria-hidden="true"
            className={`flex size-8 shrink-0 items-center justify-center rounded-full ${GLYPH_CLASSES[finding.result]}`}
          >
            <ResultIcon size={18} weight="fill" />
          </span>

          <span className="min-w-0 flex-1">
            <span className="block text-md leading-snug font-semibold tracking-tight text-text" dir="auto">
              {finding.subject_label}
            </span>
            <span className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <StatusLabel
                tone={tone}
                qualifier={finding.finding_status ? FINDING_STATUS_LABEL[finding.finding_status] : undefined}
              >
                {CHECK_RESULT_LABEL[finding.result]}
              </StatusLabel>
              {headlineDelta && (
                <span className="text-xs font-medium text-info">{FINDING_DELTA_LABEL[headlineDelta]}</span>
              )}
            </span>
          </span>

          <CaretDown
            size={16}
            weight="bold"
            aria-hidden="true"
            className={`shrink-0 text-text-subtle transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      </h3>

      <div id={bodyId} hidden={!open} className="border-t border-border">
        <div className="px-4 py-4">
          <p className="max-w-[68ch] text-base text-text-muted" dir="auto">
            {finding.message}
          </p>

          {unreviewableDocuments.length > 0 && (
            <p className="mt-3 flex items-start gap-1.5 rounded-sm bg-warning-bg px-2.5 py-1.5 text-sm text-warning">
              <WarningCircle size={15} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
              <span dir="auto">Documents non examinables : {unreviewableDocuments.map((d) => d.filename).join(", ")}</span>
            </p>
          )}

          {finding.evidence_refs.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-text-muted">
                Passages cités <span className="tabular text-text-subtle">({finding.evidence_refs.length})</span>
              </p>
              <ul className="mt-2 flex flex-col gap-2">
                {finding.evidence_refs.map((ref) => (
                  <li key={ref.fact_id}>
                    <p className="source-quote" dir="auto">
                      {ref.source_text}
                    </p>
                    <div className="mt-1.5">
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<Eye size={14} />}
                        onClick={() => onOpenDocumentPage(ref.document_id, ref.page)}
                      >
                        Voir {documentLabel(documents, ref.document_id)}, page {ref.page}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {existingResponse && (
            <div className="mt-4 rounded-sm border border-info/30 bg-info-bg px-3 py-2 text-sm text-info">
              <p className="flex items-center gap-1.5 font-semibold">
                <ChatText size={15} weight="fill" aria-hidden="true" />
                Réponse précédente enregistrée
              </p>
              {existingResponse.explanation && (
                <p className="mt-1" dir="auto">
                  {existingResponse.explanation}
                </p>
              )}
              {existingResponse.document_ids.length > 0 && (
                <p className="mt-1 text-xs">
                  Pièces jointes : {existingResponse.document_ids.map((id) => documentLabel(documents, id)).join(", ")}
                </p>
              )}
            </div>
          )}

          <details className="group mt-4">
            <summary className="inline-flex items-center gap-1.5 text-xs text-text-subtle transition-colors hover:text-text-muted">
              <CaretDown
                size={11}
                weight="bold"
                aria-hidden="true"
                className="shrink-0 transition-transform group-open:rotate-180"
              />
              Détails techniques
            </summary>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-text-muted">
              <dt className="text-text-subtle">Base</dt>
              <dd>{BASIS_LABEL[finding.basis]}</dd>

              {finding.delta && !headlineDelta && (
                <>
                  <dt className="text-text-subtle">Depuis la dernière analyse</dt>
                  <dd>{FINDING_DELTA_LABEL[finding.delta]}</dd>
                </>
              )}

              <dt className="text-text-subtle">Documents examinés</dt>
              <dd dir="auto">
                {finding.reviewed_document_ids.length > 0
                  ? finding.reviewed_document_ids.map((id) => documentLabel(documents, id)).join(", ")
                  : "aucun"}
              </dd>

              {finding.legal_reference_ids.length > 0 && (
                <>
                  <dt className="text-text-subtle">Références légales</dt>
                  <dd className="tabular">{finding.legal_reference_ids.join(", ")}</dd>
                </>
              )}

              <dt className="text-text-subtle">Vérification</dt>
              <dd className="tabular">{finding.check_id}</dd>

              <dt className="text-text-subtle">Sujet</dt>
              <dd className="tabular">{finding.subject_id}</dd>

              <dt className="text-text-subtle">Constat</dt>
              <dd className="tabular">{finding.finding_id}</dd>
            </dl>
          </details>
        </div>

        {!readOnly && onRespond && onRevisionConflict && (
          <FindingResponseForm
            finding={finding}
            revision={revision}
            activeDocuments={activeDocuments}
            onSubmitted={onRespond}
            onRevisionConflict={onRevisionConflict}
          />
        )}
      </div>
    </li>
  );
}
