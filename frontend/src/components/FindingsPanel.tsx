import { useId, useMemo, useState } from "react";
import type { Analysis, CaseDetail, CheckResult, FindingResponse, Job } from "../api/types";
import { Badge } from "./Badge";
import { FindingCard } from "./FindingCard";
import {
  ANALYSIS_STATUS_LABEL,
  ANALYSIS_STATUS_TONE,
  CHECK_RESULT_LABEL,
  EXECUTION_MODE_LABEL,
  LEGAL_COVERAGE_LABEL,
  LEGAL_COVERAGE_TONE,
} from "../lib/findingLabels";

const RESULT_FILTER_OPTIONS: Array<CheckResult | "all"> = ["all", "satisfied", "contradicted", "unassessable", "not_applicable"];
const STATUS_FILTER_OPTIONS: Array<"all" | "open" | "resolved"> = ["all", "open", "resolved"];

interface FindingsPanelProps {
  detail: CaseDetail;
  onUpdate: (revision: number, response: FindingResponse) => void;
  onReload: () => void;
  onOpenDocumentPage: (documentId: string, page: number) => void;
}

function jobMessage(job: Job | null): string {
  if (!job) return "Aucune analyse n'a encore été exécutée pour ce dossier.";
  if (job.status === "queued" || job.status === "running") {
    return "Une analyse est en cours de traitement. Revenez sur cet onglet une fois terminée.";
  }
  if (job.status === "failed") {
    return job.error
      ? `La dernière tentative d'analyse a échoué : ${job.error}`
      : "La dernière tentative d'analyse a échoué.";
  }
  return "Aucune analyse publiée n'est disponible pour ce dossier.";
}

/** "Vérifications" tab: only ever renders a backend-published analysis (frontend.md F4/FE-04). */
export function FindingsPanel({ detail, onUpdate, onReload, onOpenDocumentPage }: FindingsPanelProps) {
  const resultFilterId = useId();
  const statusFilterId = useId();
  const [resultFilter, setResultFilter] = useState<CheckResult | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "resolved">("all");

  const analysis: Analysis | null = detail.latest_analysis;
  const responseByFindingId = useMemo(() => {
    const map = new Map<string, FindingResponse>();
    for (const response of detail.responses) map.set(response.finding_id, response);
    return map;
  }, [detail.responses]);

  if (!analysis) {
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-sm text-text-muted">
        {jobMessage(detail.latest_job)}
      </div>
    );
  }

  const resultCounts = new Map<CheckResult, number>();
  for (const check of analysis.checks) resultCounts.set(check.result, (resultCounts.get(check.result) ?? 0) + 1);
  const openIssueCount = analysis.checks.filter((c) => c.finding_status === "open").length;
  const isOutdated = analysis.status === "outdated" || analysis.revision < detail.revision;

  const filteredChecks = analysis.checks.filter((check) => {
    if (resultFilter !== "all" && check.result !== resultFilter) return false;
    if (statusFilter !== "all" && check.finding_status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="flex flex-col gap-6">
      {isOutdated && (
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          Cette analyse porte sur une révision antérieure du dossier (analyse {analysis.revision} / dossier{" "}
          {detail.revision}). Une réévaluation est requise avant toute nouvelle soumission.
        </p>
      )}
      {analysis.status === "partial" && !isOutdated && (
        <p role="alert" className="rounded-sm bg-warning-bg px-3 py-2 text-sm text-warning">
          Cette analyse est partielle : certains fichiers ou vérifications n'ont pas pu être évalués. Consultez la
          couverture ci-dessous et les constats « Non évaluable ».
        </p>
      )}

      <div className="rounded-md border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={ANALYSIS_STATUS_TONE[analysis.status]}>{ANALYSIS_STATUS_LABEL[analysis.status]}</Badge>
          <Badge tone="muted">{EXECUTION_MODE_LABEL[analysis.execution_mode]}</Badge>
          <Badge tone={LEGAL_COVERAGE_TONE[analysis.legal_coverage]}>{LEGAL_COVERAGE_LABEL[analysis.legal_coverage]}</Badge>
          <span className="text-xs text-text-subtle">Checklist : {analysis.checklist_version}</span>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm text-text-muted sm:grid-cols-4">
          <div>
            <dt className="text-xs text-text-subtle">Pages examinées</dt>
            <dd className="tabular">{analysis.coverage.reviewed_pages}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Pages illisibles</dt>
            <dd className="tabular">{analysis.coverage.unreadable_pages}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Éléments rejetés</dt>
            <dd className="tabular">{analysis.coverage.rejected_facts}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Constats ouverts</dt>
            <dd className="tabular">{openIssueCount}</dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-wrap gap-2">
          {(Object.keys(CHECK_RESULT_LABEL) as CheckResult[]).map((result) => (
            <span key={result} className="text-xs text-text-muted">
              {CHECK_RESULT_LABEL[result]} : <span className="tabular">{resultCounts.get(result) ?? 0}</span>
            </span>
          ))}
        </div>

        {analysis.reconciliation && (
          <div className="mt-4 rounded-sm border border-border bg-surface-muted p-3 text-sm">
            <p className="font-medium text-text">
              Solde documenté : <span className="tabular">{analysis.reconciliation.documented_balance}</span>{" "}
              {analysis.reconciliation.currency}
            </p>
            <p className="mt-1 text-text-muted">{analysis.reconciliation.coverage_note}</p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-4">
        <div>
          <label htmlFor={resultFilterId} className="text-xs font-medium text-text-muted">
            Filtrer par résultat
          </label>
          <select
            id={resultFilterId}
            value={resultFilter}
            onChange={(e) => setResultFilter(e.target.value as CheckResult | "all")}
            className="ml-2 rounded-sm border border-border-strong bg-surface px-2 py-1 text-sm text-text"
          >
            {RESULT_FILTER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "all" ? "Tous" : CHECK_RESULT_LABEL[option]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={statusFilterId} className="text-xs font-medium text-text-muted">
            Filtrer par état
          </label>
          <select
            id={statusFilterId}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "all" | "open" | "resolved")}
            className="ml-2 rounded-sm border border-border-strong bg-surface px-2 py-1 text-sm text-text"
          >
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "all" ? "Tous" : option === "open" ? "Ouvert" : "Résolu"}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ul className="flex flex-col gap-3">
        {filteredChecks.length === 0 && (
          <li className="rounded-md border border-dashed border-border p-4 text-sm text-text-muted">
            Aucun constat ne correspond à ce filtre.
          </li>
        )}
        {filteredChecks.map((finding) => (
          <FindingCard
            key={finding.finding_id}
            finding={finding}
            revision={detail.revision}
            documents={detail.documents}
            existingResponse={responseByFindingId.get(finding.finding_id) ?? null}
            onRespond={onUpdate}
            onRevisionConflict={onReload}
            onOpenDocumentPage={onOpenDocumentPage}
          />
        ))}
      </ul>
    </div>
  );
}
