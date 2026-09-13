import { ArrowRight, CheckCircle, ListMagnifyingGlass, Warning, type Icon } from "@phosphor-icons/react";
import type { Readiness, ReadinessStatusValue } from "../api/types";
import { Button } from "./Button";
import { READINESS_LABEL } from "../lib/findingLabels";

const PANEL_CLASSES: Record<ReadinessStatusValue, string> = {
  complete: "border-success/35 bg-success-bg",
  incomplete: "border-warning/35 bg-warning-bg",
  needs_analysis: "border-border bg-surface-muted",
};

const TEXT_CLASSES: Record<ReadinessStatusValue, string> = {
  complete: "text-success",
  incomplete: "text-warning",
  needs_analysis: "text-text-muted",
};

const GLYPH_CLASSES: Record<ReadinessStatusValue, string> = {
  complete: "bg-success text-white",
  incomplete: "bg-warning text-white",
  needs_analysis: "bg-surface text-text-muted",
};

const ICON: Record<ReadinessStatusValue, Icon> = {
  complete: CheckCircle,
  incomplete: Warning,
  needs_analysis: ListMagnifyingGlass,
};

interface ReadinessNoticeProps {
  readiness: Readiness;
  /** Offered only where acting on the verdict is the next move. */
  onContinue?: () => void;
  continueLabel?: string;
}

/**
 * The automatic readiness verdict, decided by the analysis plus deterministic
 * backend checks and never by a human reviewer. Rendered wherever the preparer
 * can act on it (Vérifications and Transmission) and in the case header.
 *
 * It is deliberately a separate statement from the analysis verdict: the two can
 * honestly disagree, most visibly in fixture mode, where every check can be
 * satisfied while the case stays incomplete because no live analysis ran. Fusing
 * them would let demo data read as a transmissible dossier.
 */
export function ReadinessNotice({ readiness, onContinue, continueLabel = "Passer à la transmission" }: ReadinessNoticeProps) {
  const StatusIcon = ICON[readiness.status];

  // A named region rather than role="status": the verdict is rendered on load,
  // not announced as an update, and a second live region on the Vérifications
  // step would compete with the running-analysis announcements.
  return (
    <section
      aria-label="Verdict de complétude du dossier"
      className={`flex flex-wrap items-start gap-3 rounded-md border px-4 py-3.5 ${PANEL_CLASSES[readiness.status]}`}
    >
      <span
        aria-hidden="true"
        className={`flex size-7 shrink-0 items-center justify-center rounded-full ${GLYPH_CLASSES[readiness.status]}`}
      >
        <StatusIcon size={16} weight={readiness.status === "needs_analysis" ? "regular" : "fill"} />
      </span>

      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${TEXT_CLASSES[readiness.status]}`}>{READINESS_LABEL[readiness.status]}</p>
        {readiness.reasons.length > 0 && (
          <ul className={`mt-1.5 flex flex-col gap-1 text-sm ${TEXT_CLASSES[readiness.status]} opacity-90`}>
            {readiness.reasons.map((reason) => (
              <li key={reason} className="flex items-start gap-1.5">
                <ArrowRight size={13} aria-hidden="true" className="mt-1 shrink-0 opacity-70" />
                <span dir="auto">{reason}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {onContinue && readiness.status === "complete" && (
        <Button size="sm" onClick={onContinue} icon={<ArrowRight size={14} />}>
          {continueLabel}
        </Button>
      )}
    </section>
  );
}
