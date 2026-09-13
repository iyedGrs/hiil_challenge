import type { ReactNode } from "react";

/** Semantic-state tone (DESIGN.md "Semantic state colors"). */
export type BadgeTone = "success" | "warning" | "danger" | "info" | "muted";

const SOFT_CLASSES: Record<BadgeTone, string> = {
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  info: "bg-info-bg text-info",
  muted: "bg-muted-bg text-muted",
};

const TEXT_CLASSES: Record<BadgeTone, string> = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
  muted: "text-muted",
};

interface BadgeProps {
  tone: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
}

/**
 * Soft pill for chrome metadata: analysis status, execution mode, document
 * state, intake state. Deliberately not used for a finding's outcome, where
 * stacking three pills on one card turned the result into decoration instead
 * of an answer (see StatusLabel).
 */
export function Badge({ tone, icon, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap ${SOFT_CLASSES[tone]}`}
    >
      {icon && (
        <span aria-hidden="true" className="shrink-0">
          {icon}
        </span>
      )}
      {children}
    </span>
  );
}

interface StatusLabelProps {
  tone: BadgeTone;
  icon?: ReactNode;
  /** Secondary clause appended after the primary label, e.g. "à traiter". */
  qualifier?: string;
  children: ReactNode;
}

/**
 * A finding's outcome as typography rather than a badge: tone-coloured text
 * with one icon, optionally carrying its open/resolved qualifier on the same
 * line. One statement per card, so a scan lands on the outcome instead of
 * parsing a row of pills.
 */
export function StatusLabel({ tone, icon, qualifier, children }: StatusLabelProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${TEXT_CLASSES[tone]}`}>
      {icon && (
        <span aria-hidden="true" className="shrink-0">
          {icon}
        </span>
      )}
      <span>
        {children}
        {qualifier && <span className="font-medium opacity-80"> · {qualifier}</span>}
      </span>
    </span>
  );
}
