import { useEffect, useId, useMemo, useRef, useState } from "react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { Analysis, CaseDetail, CheckResult, FindingDelta, FindingResponse, Job } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { FindingCard } from "./FindingCard";
import { JobProgress } from "./JobProgress";
import { useJobPolling } from "../lib/useJobPolling";
import {
  ANALYSIS_STATUS_LABEL,
  ANALYSIS_STATUS_TONE,
  CHECK_RESULT_LABEL,
  EXECUTION_MODE_LABEL,
  FINDING_DELTA_LABEL,
  LEGAL_COVERAGE_LABEL,
  LEGAL_COVERAGE_TONE,
} from "../lib/findingLabels";

const RESULT_FILTER_OPTIONS: Array<CheckResult | "all"> = ["all", "satisfied", "contradicted", "unassessable", "not_applicable"];
const STATUS_FILTER_OPTIONS: Array<"all" | "open" | "resolved"> = ["all", "open", "resolved"];
const DELTA_SUMMARY_ORDER: Array<NonNullable<FindingDelta>> = ["new", "resolved", "still_open", "reopened", "not_applicable"];

interface FindingsPanelProps {
  detail: CaseDetail;
  onUpdate: (revision: number, response: FindingResponse) => void;
  onReload: () => void;
  onOpenDocumentPage: (documentId: string, page: number) => void;
}

function jobMessage(job: Job | null): string {
  if (!job) return "Aucune analyse n'a encore été exécutée pour ce dossier.";
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

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [failedJob, setFailedJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  // UI-06: reopening a case whose latest job is still active resumes polling
  // automatically; also picks up a fresher job after this tab's own job was
  // superseded (frontend.md F4 "Reopening the case restores the active job").
  useEffect(() => {
    const job = detail.latest_job;
    if (job && (job.status === "queued" || job.status === "running") && job.id !== activeJobId) {
      setActiveJobId(job.id);
      setFailedJob(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resync only when the case's own latest_job changes
  }, [detail.latest_job]);

  const polling = useJobPolling({
    jobId: activeJobId,
    onSucceeded: () => {
      setActiveJobId(null);
      setFailedJob(null);
      onReload();
    },
    onFailed: (job) => {
      setActiveJobId(null);
      setFailedJob(job);
    },
    onSuperseded: () => {
      setActiveJobId(null);
      onReload();
    },
  });

  async function handleStart(): Promise<void> {
    setStartError(null);
    setStarting(true);
    const idempotencyKey = idempotencyKeyRef.current ?? crypto.randomUUID();
    idempotencyKeyRef.current = idempotencyKey;
    try {
      const result = await caseApi.startAnalysis(detail.case_id, detail.revision, idempotencyKey);
      idempotencyKeyRef.current = null;
      setFailedJob(null);
      setActiveJobId(result.job_id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        idempotencyKeyRef.current = null;
        onReload();
      } else {
        // Idempotency key is kept so a retry of this same click reuses it.
        setStartError(err instanceof ApiError ? err.message : "Impossible de lancer l'analyse. Réessayez.");
      }
    } finally {
      setStarting(false);
    }
  }

  const analysis: Analysis | null = detail.latest_analysis;
  const isJobActive = activeJobId !== null;
  const responseByFindingId = useMemo(() => {
    const map = new Map<string, FindingResponse>();
    for (const response of detail.responses) map.set(response.finding_id, response);
    return map;
  }, [detail.responses]);

  const deltaSummary = useMemo(() => {
    if (!analysis) return null;
    const counts = new Map<FindingDelta, number>();
    for (const check of analysis.checks) {
      if (!check.delta) continue;
      counts.set(check.delta, (counts.get(check.delta) ?? 0) + 1);
    }
    return counts.size > 0 ? counts : null;
  }, [analysis]);

  const runControls = (
    <>
      {isJobActive && polling.job && (
        <JobProgress job={polling.job} stillProcessing={polling.stillProcessing} transientError={polling.transientError} />
      )}
      {failedJob && !isJobActive && (
        <div role="alert" className="rounded-md border border-danger bg-danger-bg p-4 text-sm text-danger">
          <p>{failedJob.error ?? "La dernière tentative d'analyse a échoué."}</p>
          <Button variant="secondary" className="mt-2" onClick={() => void handleStart()} disabled={starting}>
            Réessayer l'analyse
          </Button>
        </div>
      )}
      {startError && (
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {startError}
        </p>
      )}
    </>
  );

  if (!analysis) {
    return (
      <div className="flex flex-col gap-4">
        {runControls}
        {!isJobActive && !failedJob && (
          <div className="rounded-md border border-dashed border-border p-6 text-sm text-text-muted">
            <p>{jobMessage(detail.latest_job)}</p>
            <div className="mt-3">
              <Button onClick={() => void handleStart()} disabled={starting}>
                Lancer l'analyse
              </Button>
            </div>
          </div>
        )}
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
      {runControls}
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

      {deltaSummary && (
        <div className="rounded-md border border-border bg-surface-muted p-3 text-sm text-text-muted">
          <h3 className="text-xs font-medium text-text-subtle">Changements depuis la dernière analyse</h3>
          <div className="mt-1 flex flex-wrap gap-3">
            {DELTA_SUMMARY_ORDER.filter((delta) => deltaSummary.has(delta)).map((delta) => (
              <span key={delta}>
                {FINDING_DELTA_LABEL[delta]} : <span className="tabular">{deltaSummary.get(delta)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {!isJobActive && (
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => void handleStart()} disabled={starting}>
            Relancer l'analyse
          </Button>
        </div>
      )}

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
