import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { CheckCircle, Info, WarningCircle, X } from "@phosphor-icons/react";
import { IconButton } from "./Button";

export type ToastTone = "success" | "warning" | "danger" | "info";

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  notify: (tone: ToastTone, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 6_000;

const TONE_CLASSES: Record<ToastTone, string> = {
  success: "border-success/30 bg-success-bg text-success",
  warning: "border-warning/30 bg-warning-bg text-warning",
  danger: "border-danger/30 bg-danger-bg text-danger",
  info: "border-info/30 bg-info-bg text-info",
};

const TONE_ICON: Record<ToastTone, ReactNode> = {
  success: <CheckCircle size={18} weight="fill" />,
  warning: <WarningCircle size={18} weight="fill" />,
  danger: <WarningCircle size={18} weight="fill" />,
  info: <Info size={18} weight="fill" />,
};

/**
 * Transient action feedback ("Document ajouté", "Réponse enregistrée"). Toasts
 * only ever confirm something the user just did — every durable state
 * (analysis status, document state, blocking reasons) stays inline on the
 * surface it belongs to, and the fixture banner stays chrome (FE-12).
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback(
    (tone: ToastTone, message: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-2), { id, tone, message }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-40 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-6 sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-md border px-3 py-2.5 text-sm shadow-lifted animate-enter-up ${TONE_CLASSES[toast.tone]}`}
          >
            <span aria-hidden="true" className="mt-px shrink-0">
              {TONE_ICON[toast.tone]}
            </span>
            <p className="flex-1" dir="auto">
              {toast.message}
            </p>
            <IconButton
              label="Fermer cette notification"
              icon={<X size={14} />}
              onClick={() => dismiss(toast.id)}
              className="-mr-1 -mt-0.5 size-6 shrink-0 hover:bg-surface/60"
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const NOOP_TOASTS: ToastContextValue = { notify: () => {} };

/**
 * Safe outside a provider: component-level tests render panels in isolation,
 * and a missing toast host must never break the feature it decorates.
 */
export function useToast(): ToastContextValue {
  return useContext(ToastContext) ?? NOOP_TOASTS;
}
