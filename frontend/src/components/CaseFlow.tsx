import { ArrowLeft, ArrowRight, Check, Warning, type Icon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export type FlowStepState = "done" | "current" | "attention" | "todo";

export interface FlowStep {
  id: string;
  label: string;
  /** One scannable line of state, e.g. "4 pièces" or "2 points à traiter". */
  hint?: string;
  state: FlowStepState;
  icon: Icon;
  /** Blocks navigation and explains why, instead of failing silently on arrival. */
  disabledReason?: string;
}

const CIRCLE_CLASSES: Record<FlowStepState, string> = {
  done: "bg-success-bg text-success",
  current: "bg-accent text-accent-contrast",
  attention: "bg-warning-bg text-warning",
  todo: "border border-border-strong bg-surface text-text-subtle",
};

interface CaseFlowProps {
  steps: FlowStep[];
  activeId: string;
  onSelect: (id: string) => void;
  children: ReactNode;
}

/**
 * The case workspace as one ordered flow rather than four unrelated tabs.
 * Steps carry their own state (done / needs attention / not started) so the
 * rail answers "where am I and what is left" at a glance, and the footer
 * always offers the single next move — the reason the previous tab strip felt
 * like four disconnected screens sitting next to each other.
 */
export function CaseFlow({ steps, activeId, onSelect, children }: CaseFlowProps) {
  const activeIndex = Math.max(
    0,
    steps.findIndex((step) => step.id === activeId),
  );
  const activeStep = steps[activeIndex];
  const previous = activeIndex > 0 ? steps[activeIndex - 1] : null;
  const next = activeIndex < steps.length - 1 ? steps[activeIndex + 1] : null;

  return (
    <div>
      <nav aria-label="Étapes de préparation du dossier">
        <ol className="flex overflow-hidden rounded-md border border-border bg-surface shadow-raised">
          {steps.map((step, index) => {
            const active = index === activeIndex;
            const StepIcon = step.state === "done" ? Check : step.state === "attention" ? Warning : step.icon;
            return (
              <li key={step.id} className="min-w-0 flex-1 border-s border-border first:border-s-0">
                <button
                  type="button"
                  onClick={() => onSelect(step.id)}
                  disabled={step.disabledReason !== undefined}
                  aria-current={active ? "step" : undefined}
                  title={step.disabledReason}
                  className={`flex size-full items-center gap-2.5 px-3 py-3 text-start transition-colors ${
                    active ? "bg-accent-soft" : "hover:bg-surface-muted"
                  } disabled:pointer-events-none disabled:opacity-45`}
                >
                  <span
                    aria-hidden="true"
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${CIRCLE_CLASSES[step.state]}`}
                  >
                    <StepIcon size={15} weight={step.state === "done" ? "bold" : "regular"} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-sm font-medium ${active ? "text-accent" : "text-text"}`}>
                      {step.label}
                    </span>
                    {step.hint && <span className="block truncate text-xs text-text-muted">{step.hint}</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <section aria-label={activeStep?.label ?? "Étape"} className="pt-5">
        {children}
      </section>

      {(previous || next) && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          {previous ? (
            <Button variant="ghost" icon={<ArrowLeft size={15} />} onClick={() => onSelect(previous.id)}>
              {previous.label}
            </Button>
          ) : (
            <span />
          )}
          {next && (
            <Button
              variant="secondary"
              onClick={() => onSelect(next.id)}
              disabled={next.disabledReason !== undefined}
              title={next.disabledReason}
            >
              {next.label}
              <ArrowRight size={15} aria-hidden="true" />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
