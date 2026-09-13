import { ArrowRight, CaretDown, CheckCircle, Warning, WarningOctagon, type Icon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { CheckFinding } from "../api/types";
import type { AnalysisVerdict as Verdict, VerdictTone } from "../lib/verdict";
import { Button } from "./Button";
import { CHECK_RESULT_ICON, CHECK_RESULT_LABEL } from "../lib/findingLabels";

const TONE_ICON: Record<VerdictTone, Icon> = {
  success: CheckCircle,
  warning: Warning,
  danger: WarningOctagon,
};

/** The whole panel carries the state, so no colored edge rail is needed. */
const PANEL_CLASSES: Record<VerdictTone, string> = {
  success: "border-success/35 bg-success-bg",
  warning: "border-warning/35 bg-warning-bg",
  danger: "border-danger/35 bg-danger-bg",
};

const GLYPH_CLASSES: Record<VerdictTone, string> = {
  success: "bg-success text-white",
  warning: "bg-warning text-white",
  danger: "bg-danger text-white",
};

/** Secondary text on a tinted surface is derived from that hue, never gray. */
const TEXT_CLASSES: Record<VerdictTone, string> = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

function chipClasses(finding: CheckFinding): string {
  if (finding.result === "contradicted") return "border-danger/45 bg-surface text-danger hover:border-danger";
  if (finding.result === "unassessable") return "border-warning/45 bg-surface text-warning hover:border-warning";
  return "border-border-control bg-surface text-text-muted hover:border-text-muted hover:text-text";
}

interface AnalysisVerdictProps {
  verdict: Verdict;
  /** Jumps to a finding card, opens it and flashes it, so a label is a route rather than a note. */
  onFocusFinding: (findingId: string) => void;
  onRerun: () => void;
  rerunPending: boolean;
  /** Present only when the dossier can actually move to the transmission step. */
  onContinue?: () => void;
  /** Safety notice (outdated / partial coverage) shown inside the panel, with role="alert". */
  notice?: ReactNode;
}

/**
 * The answer-first panel at the top of the Vérifications step. It carries the
 * whole outcome in one line, then turns every remaining issue into a label that
 * navigates to the finding it names, so the user never reads six cards looking
 * for the one that is wrong.
 */
export function AnalysisVerdict({
  verdict,
  onFocusFinding,
  onRerun,
  rerunPending,
  onContinue,
  notice,
}: AnalysisVerdictProps) {
  const ToneIcon = TONE_ICON[verdict.tone];

  return (
    <section
      aria-labelledby="analysis-verdict-heading"
      className={`overflow-hidden rounded-md border ${PANEL_CLASSES[verdict.tone]}`}
    >
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
        <span
          aria-hidden="true"
          className={`flex size-11 shrink-0 items-center justify-center rounded-full ${GLYPH_CLASSES[verdict.tone]}`}
        >
          <ToneIcon size={24} weight="fill" />
        </span>

        <div className="min-w-0 flex-1">
          <h2
            id="analysis-verdict-heading"
            className={`text-lg leading-tight font-semibold tracking-tighter ${TEXT_CLASSES[verdict.tone]}`}
          >
            {verdict.headline}
          </h2>
          <p className={`mt-1.5 max-w-[62ch] text-sm ${TEXT_CLASSES[verdict.tone]} opacity-90`}>{verdict.detail}</p>
          {notice && <div className={`mt-3 text-sm font-medium ${TEXT_CLASSES[verdict.tone]}`}>{notice}</div>}
        </div>

        <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
          {onContinue && (
            <Button onClick={onContinue} icon={<ArrowRight size={16} />}>
              Passer à la transmission
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onRerun} pending={rerunPending}>
            Relancer l'analyse
          </Button>
        </div>
      </div>

      {verdict.issues.length > 0 && (
        <div className="border-t border-current/15 bg-surface/55 px-5 py-4">
          <p className="text-xs font-medium text-text-muted">Aller directement au constat concerné</p>
          <ul className="mt-2.5 flex flex-wrap gap-2">
            {verdict.issues.map((finding) => {
              const ResultIcon = CHECK_RESULT_ICON[finding.result];
              return (
                <li key={finding.finding_id} className="max-w-full">
                  <button
                    type="button"
                    onClick={() => onFocusFinding(finding.finding_id)}
                    className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors active:translate-y-px ${chipClasses(finding)}`}
                  >
                    <ResultIcon size={15} weight="fill" aria-hidden="true" className="shrink-0" />
                    <span className="truncate" dir="auto">
                      {finding.subject_label}
                    </span>
                    <span className="sr-only"> ({CHECK_RESULT_LABEL[finding.result]})</span>
                    <CaretDown size={13} weight="bold" aria-hidden="true" className="shrink-0 opacity-60" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
