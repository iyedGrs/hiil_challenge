import type { ButtonHTMLAttributes, ComponentPropsWithRef, ReactNode } from "react";

/**
 * Intent decides the variant, not visual balance:
 * - `primary`   accent fill. Submit, confirm, advance the flow.
 * - `secondary` bordered neutral. Everything reversible.
 * - `ghost`     text only. Tertiary and in-place toggles.
 * - `danger`    solid red fill. The confirming step of a destructive action.
 * - `dangerQuiet` red text. Offering a destructive action before it is confirmed.
 */
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "dangerQuiet";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Leading glyph from an allowed icon library, never a hand-rolled SVG path. */
  icon?: ReactNode;
  /** Work is in flight: shows an indeterminate sweep and marks the control busy. */
  pending?: boolean;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-contrast shadow-action hover:bg-accent-hover",
  secondary: "border border-border-control bg-surface text-text hover:border-text-muted hover:bg-surface-muted",
  ghost: "text-text-muted hover:bg-surface-muted hover:text-text",
  danger: "bg-danger text-white shadow-raised hover:brightness-90",
  dangerQuiet: "border border-danger/45 bg-surface text-danger hover:border-danger hover:bg-danger-bg",
};

/** The sweep tints itself from the button's own foreground, so it reads on every variant. */
const SWEEP_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-accent-contrast/70",
  secondary: "bg-accent/60",
  ghost: "bg-accent/60",
  danger: "bg-white/70",
  dangerQuiet: "bg-danger/60",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "gap-1.5 px-2.5 py-1.5 text-xs",
  md: "gap-2 px-4 py-2 text-sm",
};

/**
 * Shared button primitive. Implements the whole interactive cycle DESIGN.md
 * requires: default, hover, focus-visible, a tactile press, pending and
 * disabled.
 */
export function Button({
  variant = "primary",
  size = "md",
  icon,
  pending,
  className = "",
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={`relative inline-flex items-center justify-center overflow-hidden rounded-sm font-medium tracking-tight transition-[background-color,border-color,color,box-shadow,translate,filter] active:translate-y-px disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {icon && (
        <span aria-hidden="true" className="shrink-0">
          {icon}
        </span>
      )}
      {children}
      {pending && (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden">
          <span className={`block size-full animate-sweep ${SWEEP_CLASSES[variant]}`} />
        </span>
      )}
    </button>
  );
}

interface IconButtonProps extends ComponentPropsWithRef<"button"> {
  /** Required: an icon-only control has no visible text to name it. */
  label: string;
  icon: ReactNode;
  variant?: Extract<ButtonVariant, "secondary" | "ghost">;
}

/** Square icon-only control (tile menus, drawer close, dismiss). */
export function IconButton({ label, icon, variant = "ghost", className = "", ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`inline-flex size-8 items-center justify-center rounded-sm transition-colors active:translate-y-px disabled:pointer-events-none disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}
