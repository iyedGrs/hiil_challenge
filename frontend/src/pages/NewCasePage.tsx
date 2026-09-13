import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft } from "@phosphor-icons/react";
import { caseApi, dataMode } from "../api";
import { ApiError } from "../api/ApiError";
import type { Claim } from "../api/types";
import { IntakeForm, type IntakeFormResult } from "../components/IntakeForm";
import { useSession } from "../session/SessionContext";

const BLANK_CLAIM: Claim = {
  case_type: "",
  claimant_name: "",
  counterparty_name: "",
  claimed_amount: "",
  currency: "",
  dates: { contract: null, delivery: null, invoice: null, payment_due: null },
  requested_outcome: "",
  narrative: "",
  follow_up_answers: [],
};

export function NewCasePage() {
  const { config } = useSession();
  const navigate = useNavigate();

  async function handleSubmit(claim: Claim): Promise<IntakeFormResult> {
    try {
      const { case_id } = await caseApi.createCase(claim);
      // Created regardless of intake status — a draft is kept even when more
      // information is needed (frontend.md F4). The case screen drives the
      // follow-up/edit step from here.
      navigate(`/cases/${case_id}`, { replace: true });
      return { ok: true };
    } catch (err) {
      if (err instanceof ApiError) {
        return { ok: false, fieldErrors: err.fieldErrors, message: err.fieldErrors.length === 0 ? err.message : undefined };
      }
      return { ok: false, fieldErrors: [], message: "Une erreur inattendue s'est produite. Réessayez." };
    }
  }

  if (!config) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10">
        <p role="alert" className="text-sm text-danger">
          La configuration du serveur est indisponible. Rechargez la page pour réessayer.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <Link
        to="/cases"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-text-muted no-underline transition-colors hover:text-accent"
      >
        <ArrowLeft size={15} aria-hidden="true" />
        Mes dossiers
      </Link>

      <h1 className="mt-3 text-xl font-semibold text-text">Nouveau dossier</h1>
      <p className="mt-1 max-w-[65ch] text-sm text-text-muted">
        Décrivez le litige contractuel. Vous ajouterez les pièces justificatives à l'étape suivante.
        {dataMode === "fixture" && " Données de démonstration uniquement."}
      </p>

      <div className="mt-6 rounded-md border border-border bg-surface p-5 shadow-raised">
        <IntakeForm
          config={config}
          initialClaim={BLANK_CLAIM}
          questions={[]}
          submitLabel="Créer le dossier"
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  );
}
