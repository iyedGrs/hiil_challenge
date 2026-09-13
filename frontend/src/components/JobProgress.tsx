import type { Job, JobPhase } from "../api/types";

/** Exact running-phase order per spec/backend.md B9 ("Running phases: reading, extracting, validating_facts, checking, validating_checks, publishing"). */
const RUNNING_PHASES: JobPhase[] = ["reading", "extracting", "validating_facts", "checking", "validating_checks", "publishing"];

const PHASE_LABEL: Record<JobPhase, string> = {
  reading: "Lecture des documents",
  extracting: "Extraction des données",
  validating_facts: "Validation des faits",
  checking: "Vérification des constats",
  validating_checks: "Validation des vérifications",
  publishing: "Publication du résultat",
  // PROVISIONAL (B9 gap): export jobs reuse this component's phase type but
  // B9 only names `packaging` for exports, not a UI label.
  packaging: "Génération du dossier",
};

interface JobProgressProps {
  job: Job;
  stillProcessing: boolean;
  transientError: boolean;
}

function statusText(job: Job): string {
  if (job.status === "queued") return "Analyse en file d'attente…";
  if (job.phase) return `Analyse en cours : ${PHASE_LABEL[job.phase]}…`;
  return "Analyse en cours…";
}

/** Step indicator for a running analysis job (frontend.md F4: honest job states + phases, aria-live status). */
export function JobProgress({ job, stillProcessing, transientError }: JobProgressProps) {
  const currentIndex = job.phase ? RUNNING_PHASES.indexOf(job.phase) : -1;

  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <ol className="flex flex-wrap gap-2">
        {RUNNING_PHASES.map((phase, index) => (
          <li
            key={phase}
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              index < currentIndex
                ? "bg-success-bg text-success"
                : index === currentIndex
                  ? "bg-info-bg text-info"
                  : "bg-muted-bg text-muted"
            }`}
          >
            {PHASE_LABEL[phase]}
          </li>
        ))}
      </ol>
      <p role="status" aria-live="polite" className="mt-2 text-sm text-text-muted">
        {statusText(job)}
      </p>
      {stillProcessing && (
        <p role="status" aria-live="polite" className="mt-2 rounded-sm bg-info-bg px-3 py-2 text-sm text-info">
          Toujours en cours de traitement…
        </p>
      )}
      {transientError && (
        <p role="status" aria-live="polite" className="mt-2 rounded-sm bg-warning-bg px-3 py-2 text-sm text-warning">
          Connexion instable ; nouvelle tentative en cours. Le traitement côté serveur continue normalement.
        </p>
      )}
    </div>
  );
}
