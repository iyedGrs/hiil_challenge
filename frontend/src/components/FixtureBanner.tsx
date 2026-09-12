/** Persistent, non-dismissible per FE-12 and DESIGN.md — never a toast that can be missed or auto-hidden. */
export function FixtureBanner() {
  return (
    <div role="status" className="w-full border-b border-border bg-warning-bg px-4 py-2 text-center text-xs text-warning">
      Données de démonstration — aucune analyse réelle en cours.
    </div>
  );
}
