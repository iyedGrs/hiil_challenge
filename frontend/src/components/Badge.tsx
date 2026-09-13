/** Semantic-state pill (DESIGN.md "Semantic state colors"). Used for intake/document/job/check states. */
export type BadgeTone = "success" | "warning" | "danger" | "info" | "muted";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  info: "bg-info-bg text-info",
  muted: "bg-muted-bg text-muted",
};

interface BadgeProps {
  tone: BadgeTone;
  children: React.ReactNode;
}

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}
