import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CaretRight, FolderSimplePlus, Plus } from "@phosphor-icons/react";
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
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-xl font-semibold text-text">Mes dossiers</h1>
          <p className="mt-1 text-sm text-text-muted">
            Reprenez une préparation en cours, ou démarrez une nouvelle réclamation.
          </p>
        </div>
        <Link to="/cases/new" className="no-underline">
          <Button variant="primary" icon={<Plus size={15} weight="bold" />}>
            Nouveau dossier
          </Button>
        </Link>
      </div>

      {state.status === "loading" && (
        <ul className="mt-6 flex flex-col gap-3" aria-label="Chargement des dossiers">
          {[0, 1, 2].map((i) => (
            <li key={i} className="skeleton h-[86px] rounded-md border border-border" />
          ))}
        </ul>
      )}

      {state.status === "error" && (
        <p role="alert" className="mt-6 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      )}

      {state.status === "loaded" && state.cases.length === 0 && (
        <div className="mt-6 rounded-md border border-dashed border-border-strong bg-surface p-10 text-center">
          <span
            aria-hidden="true"
            className="mx-auto flex size-12 items-center justify-center rounded-full bg-surface-muted text-text-subtle"
          >
            <FolderSimplePlus size={26} />
          </span>
          <h2 className="mt-4 text-md font-semibold text-text">Aucun dossier pour l'instant</h2>
          <p className="mx-auto mt-1 max-w-[48ch] text-sm text-text-muted">
            Un dossier regroupe votre réclamation, les pièces justificatives et le résultat des vérifications.
          </p>
          <Link to="/cases/new" className="mt-5 inline-block no-underline">
            <Button variant="primary" icon={<Plus size={15} weight="bold" />}>
              Créer un dossier
            </Button>
          </Link>
        </div>
      )}

      {state.status === "loaded" && state.cases.length > 0 && (
        <ul className="mt-6 flex flex-col gap-3">
          {state.cases.map((c) => (
            <li key={c.case_id}>
              <Link
                to={`/cases/${c.case_id}`}
                className="group flex items-center gap-4 rounded-md border border-border bg-surface p-4 no-underline shadow-raised transition-[border-color,box-shadow] hover:border-border-strong hover:shadow-lifted"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-md font-medium text-text transition-colors group-hover:text-accent" dir="auto">
                    {c.claimant_name} <span className="font-normal text-text-subtle">c.</span> {c.counterparty_name}
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    Révision <span className="tabular">{c.revision}</span> · mis à jour le{" "}
                    <span className="tabular">{new Date(c.updated_at).toLocaleString("fr-FR")}</span>
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  <p className="tabular text-md font-semibold text-text">
                    {c.claimed_amount} <span className="text-xs font-normal text-text-muted">{c.currency}</span>
                  </p>
                  <Badge tone={INTAKE_STATUS_TONE[c.intake_status]}>{INTAKE_STATUS_LABEL[c.intake_status]}</Badge>
                </div>
                <CaretRight
                  size={17}
                  aria-hidden="true"
                  className="shrink-0 text-text-subtle transition-colors group-hover:text-accent"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
