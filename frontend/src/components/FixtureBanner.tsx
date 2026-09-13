import { Flask } from "@phosphor-icons/react";

/** Persistent, non-dismissible per FE-12 and DESIGN.md: never a toast that can be missed or auto-hidden. */
export function FixtureBanner() {
  return (
    <div
      role="status"
      className="flex w-full items-center justify-center gap-1.5 border-b border-warning/30 bg-warning-bg px-4 py-2 text-center text-xs text-warning"
    >
      <Flask size={14} aria-hidden="true" className="shrink-0" />
      Données de démonstration. Aucune analyse réelle n'est en cours.
    </div>
  );
}
