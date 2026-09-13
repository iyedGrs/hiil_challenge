import { useEffect, useRef } from "react";
import { ChatCircleDots, X } from "@phosphor-icons/react";
import type { ActivityEvent } from "../api/types";
import { IconButton } from "./Button";

interface ActivityDrawerProps {
  open: boolean;
  onClose: () => void;
  activity: ActivityEvent[];
}

/**
 * The case activity log, moved out of the workspace flow into an on-demand
 * panel (UI-08 still surfaces reviewer clarification requests here). It is
 * reference material consulted occasionally, so it no longer occupies a step
 * the preparer has to walk past on every visit.
 */
export function ActivityDrawer({ open, onClose, activity }: ActivityDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  const sorted = [...activity].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <>
      <div
        aria-hidden="true"
        onClick={onClose}
        className="fixed inset-0 z-30 bg-text/25 animate-fade-in"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="activity-drawer-title"
        tabIndex={-1}
        className="fixed inset-y-0 end-0 z-30 flex w-full max-w-md flex-col border-s border-border bg-surface shadow-overlay animate-enter-right"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <h2 id="activity-drawer-title" className="text-md font-semibold text-text">
            Historique du dossier
          </h2>
          <IconButton label="Fermer l'historique" icon={<X size={17} />} onClick={onClose} />
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {sorted.length === 0 ? (
            <p className="text-sm text-text-muted">Aucune activité pour l'instant.</p>
          ) : (
            <ol className="flex flex-col">
              {sorted.map((event, index) => {
                const isClarification = event.type === "reviewer_clarification_requested";
                return (
                  <li key={event.id} className="flex gap-3">
                    {/* Timeline spine: the connector stops at the last entry. */}
                    <div className="flex flex-col items-center pt-1.5" aria-hidden="true">
                      <span
                        className={`size-2.5 shrink-0 rounded-full ${
                          isClarification ? "bg-warning" : "bg-border-strong"
                        }`}
                      />
                      {index < sorted.length - 1 && <span className="w-px flex-1 bg-border" />}
                    </div>
                    <div className={`min-w-0 flex-1 pb-5 ${index === sorted.length - 1 ? "pb-0" : ""}`}>
                      <p className="tabular text-xs text-text-subtle">
                        {new Date(event.created_at).toLocaleString("fr-FR")}
                      </p>
                      <p
                        className={`mt-0.5 text-sm ${
                          isClarification
                            ? "rounded-sm bg-warning-bg px-2.5 py-1.5 font-medium text-warning"
                            : "text-text"
                        }`}
                        dir="auto"
                      >
                        {isClarification && (
                          <ChatCircleDots size={15} weight="fill" aria-hidden="true" className="me-1.5 inline align-[-2px]" />
                        )}
                        {event.message}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </>
  );
}
