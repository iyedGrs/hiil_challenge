import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CaseSummary } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { INTAKE_STATUS_LABEL, INTAKE_STATUS_TONE } from "../lib/intakeStatus";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; cases: CaseSummary[] };

export function CasesListPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    caseApi
      .listCases()
      .then(({ items }) => {
        if (!cancelled) setState({ status: "loaded", cases: items });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Impossible de charger vos dossiers.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text">Mes dossiers</h1>
        <Link to="/cases/new">
          <Button variant="primary">Nouveau dossier</Button>
        </Link>
      </div>

      {state.status === "loading" && (
        <ul className="mt-6 flex flex-col gap-3" aria-label="Chargement des dossiers">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-20 animate-pulse rounded-md border border-border bg-surface-muted" />
          ))}
        </ul>
      )}

      {state.status === "error" && (
        <p role="alert" className="mt-6 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      )}

      {state.status === "loaded" && state.cases.length === 0 && (
        <div className="mt-6 rounded-md border border-border bg-surface p-8 text-center">
          <p className="text-sm text-text-muted">Aucun dossier pour l'instant — créez-en un.</p>
          <Link to="/cases/new" className="mt-4 inline-block">
            <Button variant="primary">Créer un dossier</Button>
          </Link>
        </div>
      )}

      {state.status === "loaded" && state.cases.length > 0 && (
        <ul className="mt-6 flex flex-col gap-3">
          {state.cases.map((c) => (
            <li key={c.case_id}>
              <Link
                to={`/cases/${c.case_id}`}
                className="block rounded-md border border-border bg-surface p-4 transition-colors hover:border-border-strong"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-md font-medium text-text">
                      {c.claimant_name} <span className="text-text-subtle">c.</span> {c.counterparty_name}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      Révision <span className="tabular">{c.revision}</span> · mis à jour le{" "}
                      <span className="tabular">{new Date(c.updated_at).toLocaleString("fr-FR")}</span>
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <p className="tabular text-md font-semibold text-text">
                      {c.claimed_amount} {c.currency}
                    </p>
                    <Badge tone={INTAKE_STATUS_TONE[c.intake_status]}>{INTAKE_STATUS_LABEL[c.intake_status]}</Badge>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
