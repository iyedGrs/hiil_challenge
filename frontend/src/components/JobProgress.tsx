import { useEffect, useState } from "react";
import { Check, WarningCircle, WifiSlash } from "@phosphor-icons/react";
import type { Job, JobPhase } from "../api/types";

/** Exact running-phase order per spec/backend.md B9 ("Running phases: reading, extracting, validating_facts, checking, validating_checks, publishing"). */
const RUNNING_PHASES: JobPhase[] = ["reading", "extracting", "validating_facts", "checking", "validating_checks", "publishing"];

/** Export jobs run a single packaging phase (B9). */
export const EXPORT_PHASES: JobPhase[] = ["packaging"];

const PHASE_LABEL: Record<JobPhase, string> = {
  reading: "Lecture des documents",
  extracting: "Extraction des données",
  validating_facts: "Validation des faits",
  checking: "Vérification des constats",
  validating_checks: "Validation des vérifications",
  publishing: "Publication du résultat",
  // PROVISIONAL (B9 gap): export jobs reuse this component's phase type but
  // B9 only names `packaging` for exports, not a UI label.
  packaging: "Assemblage des pièces",
};

/** What each phase is actually doing, so a waiting user has something to read. */
const PHASE_DETAIL: Record<JobPhase, string> = {
  reading: "Ouverture de chaque page et récupération du texte lisible.",
  extracting: "Relevé des montants, dates et références cités dans les pièces.",
  validating_facts: "Chaque donnée relevée est rattachée à sa page d'origine.",
  checking: "Comparaison des pièces avec la liste de contrôle du dossier.",
  validating_checks: "Contrôle que chaque constat cite bien une source.",
  publishing: "Enregistrement du résultat sur le dossier.",
  packaging: "Regroupement des pièces et des constats dans un dossier à télécharger.",
};

interface JobProgressProps {
  job: Job;
  stillProcessing: boolean;
  transientError: boolean;
  /** Phase rail to render; defaults to the analysis pipeline. */
  phases?: JobPhase[];
  /** Subject of the live status sentence, e.g. "Analyse" or "Génération du dossier". */
  label?: string;
}

function statusText(job: Job, label: string): string {
  if (job.status === "queued") return `${label} en file d'attente…`;
  if (job.phase) return `${label} en cours : ${PHASE_LABEL[job.phase]}…`;
  return `${label} en cours…`;
}

function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setSeconds((s) => s + 1), 1_000);
    return () => clearInterval(timer);
  }, [active]);
  return seconds;
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Running-job feedback (frontend.md F4: honest job states + phases, aria-live
 * status). The rail is deliberately not a spinner: it names the pipeline
 * phase the server actually reports, marks everything before it done, and
 * animates only the one segment that is genuinely in flight — so a long wait
 * still reads as progress rather than a hang.
 */
export function JobProgress({
  job,
  stillProcessing,
  transientError,
  phases = RUNNING_PHASES,
  label = "Analyse",
}: JobProgressProps) {
  const currentIndex = job.phase ? phases.indexOf(job.phase) : -1;
  const elapsed = useElapsedSeconds(job.status === "queued" || job.status === "running");

  return (
    <div className="overflow-hidden rounded-md border border-border bg-surface shadow-raised">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-4 py-3">
        <h3 className="text-md font-semibold text-text">{label} en cours</h3>
        <p className="tabular text-xs text-text-subtle">{formatElapsed(elapsed)}</p>
      </div>

      {/* Segmented track: one segment per server-reported phase. */}
      <ol className="flex gap-1 px-4 pt-4" aria-hidden="true">
        {phases.map((phase, index) => (
          <li
            key={phase}
            className={`relative h-1 flex-1 overflow-hidden rounded-full ${
              index < currentIndex ? "bg-accent" : "bg-surface-muted"
            }`}
          >
            {index === currentIndex && (
              <span className="absolute inset-0 origin-left rounded-full bg-accent animate-track" />
            )}
          </li>
        ))}
      </ol>

      <ol className="flex flex-col gap-3 px-4 py-4">
        {phases.map((phase, index) => {
          const done = index < currentIndex;
          const active = index === currentIndex;
          return (
            <li key={phase} className="flex items-start gap-3">
              <span className="relative mt-0.5 flex size-5 shrink-0 items-center justify-center">
                {done ? (
                  <span className="flex size-5 items-center justify-center rounded-full bg-success-bg text-success">
                    <Check size={12} weight="bold" aria-hidden="true" />
                  </span>
                ) : active ? (
                  <>
                    <span className="absolute size-3 rounded-full bg-accent/40 animate-halo" />
                    <span className="size-2.5 rounded-full bg-accent animate-breathe" />
                  </>
                ) : (
                  <span className="size-2.5 rounded-full border border-border-strong" />
                )}
              </span>
              <div className="min-w-0">
                <p
                  className={`text-sm ${
                    active ? "font-semibold text-text" : done ? "text-text-muted" : "text-text-subtle"
                  }`}
                >
                  {PHASE_LABEL[phase]}
                </p>
                {active && <p className="mt-0.5 text-xs text-text-muted">{PHASE_DETAIL[phase]}</p>}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="border-t border-border bg-surface-muted px-4 py-3">
        <p role="status" aria-live="polite" className="text-sm text-text-muted">
          {statusText(job, label)}
        </p>
        {stillProcessing && (
          <p role="status" aria-live="polite" className="mt-2 flex items-start gap-2 text-sm text-info">
            <WarningCircle size={16} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
            Toujours en cours de traitement…
          </p>
        )}
        {transientError && (
          <p role="status" aria-live="polite" className="mt-2 flex items-start gap-2 text-sm text-warning">
            <WifiSlash size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            Connexion instable ; nouvelle tentative en cours. Le traitement côté serveur continue normalement.
          </p>
        )}
      </div>
    </div>
  );
}
