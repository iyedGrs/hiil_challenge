import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ArrowClockwise, CaretDown, FunnelSimple, ListMagnifyingGlass, Play, WarningCircle } from "@phosphor-icons/react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { Analysis, CaseDetail, CheckResult, FindingDelta, FindingResponse, Job } from "../api/types";
import { AnalysisVerdict } from "./AnalysisVerdict";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { FindingCard } from "./FindingCard";
import { JobProgress } from "./JobProgress";
import { useToast } from "./Toast";
import { useJobPolling } from "../lib/useJobPolling";
import { buildVerdict, sortChecksForReview } from "../lib/verdict";
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

const SELECT_CLASSES =
  "rounded-sm border border-border-control bg-surface px-2 py-1 text-xs text-text transition-colors hover:border-text-muted";

const FLASH_DURATION_MS = 2_000;

interface FindingsPanelProps {
  detail: CaseDetail;
  onUpdate: (revision: number, response: FindingResponse) => void;
  onReload: () => void;
  onOpenDocumentPage: (documentId: string, page: number) => void;
  /** Advances the case flow to the transmission step; omitted in read-only contexts. */
  onNavigateToSubmission?: () => void;
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

/** "Vérifications" step: only ever renders a backend-published analysis (frontend.md F4/FE-04). */
export function FindingsPanel({
  detail,
  onUpdate,
  onReload,
  onOpenDocumentPage,
  onNavigateToSubmission,
}: FindingsPanelProps) {
  const resultFilterId = useId();
  const statusFilterId = useId();
  const { notify } = useToast();
  const [resultFilter, setResultFilter] = useState<CheckResult | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | "resolved">("all");
  const [flashedFindingId, setFlashedFindingId] = useState<string | null>(null);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [failedJob, setFailedJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  // UI-06: reopening a case whose latest job is still active resumes polling
  // automatically; also picks up a fresher job after this step's own job was
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
      notify("success", "Analyse terminée. Le résultat ci-dessous est à jour.");
      onReload();
    },
    onFailed: (job) => {
      setActiveJobId(null);
      setFailedJob(job);
      notify("danger", job.error ?? "La dernière tentative d'analyse a échoué.");
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

  /**
   * Verdict label to finding card. Clears the filters first (a filtered-out card
   * cannot be jumped to), then moves both the viewport and keyboard focus so the
   * jump works for pointer and screen-reader users alike.
   */
  function focusFinding(findingId: string): void {
    setResultFilter("all");
    setStatusFilter("all");
    setFlashedFindingId(findingId);
    window.setTimeout(() => {
      const target = document.getElementById(`finding-${findingId}`);
      if (!target) return;
      target.scrollIntoView?.({ behavior: "smooth", block: "start" });
      target.setAttribute("tabindex", "-1");
      target.focus?.({ preventScroll: true });
    }, 0);
    window.setTimeout(
      () => setFlashedFindingId((current) => (current === findingId ? null : current)),
      FLASH_DURATION_MS,
    );
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
        <div role="alert" className="rounded-md border border-danger/40 bg-danger-bg p-4 text-sm text-danger">
          <p className="flex items-start gap-2 font-medium">
            <WarningCircle size={17} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
            {failedJob.error ?? "La dernière tentative d'analyse a échoué."}
          </p>
          <Button
            variant="secondary"
            size="sm"
            icon={<ArrowClockwise size={14} />}
            className="mt-3"
            onClick={() => void handleStart()}
            pending={starting}
          >
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
          <div className="rounded-md border border-dashed border-border-strong bg-surface p-8 text-center">
            <span
              aria-hidden="true"
              className="mx-auto flex size-11 items-center justify-center rounded-full bg-accent-soft text-accent"
            >
              <ListMagnifyingGlass size={24} />
            </span>
            <h2 className="mt-3 text-md font-semibold tracking-tight text-text">Prêt à vérifier vos pièces</h2>
            <p className="mx-auto mt-1 max-w-[52ch] text-sm text-text-muted">{jobMessage(detail.latest_job)}</p>
            <div className="mt-4 flex justify-center">
              <Button icon={<Play size={15} weight="fill" />} onClick={() => void handleStart()} pending={starting}>
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
  const isPartial = analysis.status === "partial" && !isOutdated;
  const verdict = buildVerdict(analysis, detail.revision);

  const filteredChecks = sortChecksForReview(analysis.checks).filter((check) => {
    if (resultFilter !== "all" && check.result !== resultFilter) return false;
    if (statusFilter !== "all" && check.finding_status !== statusFilter) return false;
    return true;
  });

  const canContinue = !isOutdated && !isJobActive && onNavigateToSubmission !== undefined;

  // One statement, inside the verdict panel, instead of a second stacked banner.
  const notice = isOutdated ? (
    <p role="alert">
      Une réévaluation est requise avant toute nouvelle soumission (analyse {analysis.revision}, dossier{" "}
      {detail.revision}).
    </p>
  ) : isPartial ? (
    <p role="alert">
      Analyse partielle : certains fichiers ou vérifications n'ont pas pu être évalués. Les constats « Non évaluable »
      ci-dessous en portent la trace.
    </p>
  ) : null;

  return (
    <div className="flex flex-col gap-4">
      {runControls}

      <AnalysisVerdict
        verdict={verdict}
        onFocusFinding={focusFinding}
        onRerun={() => void handleStart()}
        rerunPending={starting || isJobActive}
        onContinue={canContinue ? onNavigateToSubmission : undefined}
        notice={notice}
      />

      {analysis.reconciliation && (
        <div className="rounded-md border border-border bg-surface p-4 shadow-raised">
          <p className="text-xs font-medium text-text-muted">Solde documenté</p>
          <p className="tabular mt-1 text-lg font-semibold tracking-tighter text-text">
            <span>{analysis.reconciliation.documented_balance}</span>{" "}
            <span className="text-sm font-medium text-text-muted">{analysis.reconciliation.currency}</span>
          </p>
          <p className="mt-1.5 max-w-[68ch] text-sm text-text-muted">{analysis.reconciliation.coverage_note}</p>
        </div>
      )}

      {/*
       * Everything below the verdict is context, not the answer, so it collapses.
       * The summary line keeps the three facts that qualify the whole analysis
       * visible at all times: publication state, execution mode, legal coverage.
       */}
      <details className="group rounded-md border border-border bg-surface shadow-raised">
        <summary className="flex flex-wrap items-center gap-2 px-4 py-3 transition-colors hover:bg-surface-muted">
          <Badge tone={ANALYSIS_STATUS_TONE[analysis.status]}>{ANALYSIS_STATUS_LABEL[analysis.status]}</Badge>
          <Badge tone="muted">{EXECUTION_MODE_LABEL[analysis.execution_mode]}</Badge>
          <Badge tone={LEGAL_COVERAGE_TONE[analysis.legal_coverage]}>{LEGAL_COVERAGE_LABEL[analysis.legal_coverage]}</Badge>
          <span className="ms-auto inline-flex items-center gap-1.5 text-xs font-medium text-text-muted">
            Détail de l'analyse
            <CaretDown size={12} weight="bold" aria-hidden="true" className="transition-transform group-open:rotate-180" />
          </span>
        </summary>

        <div className="border-t border-border px-4 py-4">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-text-subtle">Pages examinées</dt>
              <dd className="tabular mt-0.5 text-md font-semibold text-text">{analysis.coverage.reviewed_pages}</dd>
            </div>
            <div>
              <dt className="text-xs text-text-subtle">Pages illisibles</dt>
              <dd className="tabular mt-0.5 text-md font-semibold text-text">{analysis.coverage.unreadable_pages}</dd>
            </div>
            <div>
              <dt className="text-xs text-text-subtle">Éléments rejetés</dt>
              <dd className="tabular mt-0.5 text-md font-semibold text-text">{analysis.coverage.rejected_facts}</dd>
            </div>
            <div>
              <dt className="text-xs text-text-subtle">Constats ouverts</dt>
              <dd className="tabular mt-0.5 text-md font-semibold text-text">{openIssueCount}</dd>
            </div>
          </dl>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-border pt-3 sm:grid-cols-4">
            {(Object.keys(CHECK_RESULT_LABEL) as CheckResult[]).map((result) => (
              <div key={result} className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-text-muted">{CHECK_RESULT_LABEL[result]}</dt>
                <dd className="tabular text-xs font-semibold text-text">{resultCounts.get(result) ?? 0}</dd>
              </div>
            ))}
          </dl>

          {deltaSummary && (
            <div className="mt-4 border-t border-border pt-3">
              <h3 className="text-xs font-medium text-text-muted">Changements depuis la dernière analyse</h3>
              <dl className="mt-1.5 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
                {DELTA_SUMMARY_ORDER.filter((delta) => deltaSummary.has(delta)).map((delta) => (
                  <div key={delta} className="flex items-baseline justify-between gap-2">
                    <dt className="text-xs text-text-muted">{FINDING_DELTA_LABEL[delta]}</dt>
                    <dd className="tabular text-xs font-semibold text-text">{deltaSummary.get(delta)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      </details>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border pb-2.5">
        <h2 className="text-md font-semibold tracking-tight text-text">
          Constats <span className="tabular text-sm font-medium text-text-subtle">{analysis.checks.length}</span>
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <FunnelSimple size={14} aria-hidden="true" className="text-text-subtle" />
          <div className="flex items-center gap-1.5">
            <label htmlFor={resultFilterId} className="text-xs text-text-muted">
              Filtrer par résultat
            </label>
            <select
              id={resultFilterId}
              value={resultFilter}
              onChange={(e) => setResultFilter(e.target.value as CheckResult | "all")}
              className={SELECT_CLASSES}
            >
              {RESULT_FILTER_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "Tous" : CHECK_RESULT_LABEL[option]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <label htmlFor={statusFilterId} className="text-xs text-text-muted">
              Filtrer par état
            </label>
            <select
              id={statusFilterId}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "all" | "open" | "resolved")}
              className={SELECT_CLASSES}
            >
              {STATUS_FILTER_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "Tous" : option === "open" ? "À traiter" : "Résolus"}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <ul aria-label="Constats" className="flex flex-col gap-2.5">
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
            flash={flashedFindingId === finding.finding_id}
          />
        ))}
      </ul>
    </div>
  );
}
