import { useId, type ReactNode } from "react";

interface FormFieldProps {
  label: string;
  error?: string | null;
  hint?: string | null;
  /** Follow-up question copy shown as clarification, never as "analysis failed" (frontend.md F4). */
  followUp?: string | null;
  required?: boolean;
  children: (fieldProps: { id: string; "aria-describedby"?: string; "aria-invalid"?: true }) => ReactNode;
}

/** Label + input + error/hint wrapper wired for aria-describedby (FE-10, FE-02). Reused across every intake field. */
export function FormField({ label, error, hint, followUp, required, children }: FormFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const followUpId = `${id}-followup`;

  const describedBy = [error ? errorId : null, followUp ? followUpId : null, hint ? hintId : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children({
        id,
        "aria-describedby": describedBy || undefined,
        ...(error ? { "aria-invalid": true } : {}),
      })}
      {followUp && (
        <p id={followUpId} className="rounded-sm bg-warning-bg px-2.5 py-1.5 text-sm text-warning">
          {followUp}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className="text-xs text-text-subtle">
          {hint}
        </p>
      )}
    </div>
  );
}
