import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CaseDetail, Claim } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { IntakeForm, type IntakeFormResult } from "../components/IntakeForm";
import { Tabs } from "../components/Tabs";
import { useSession } from "../session/SessionContext";
import { INTAKE_STATUS_LABEL, INTAKE_STATUS_TONE } from "../lib/intakeStatus";

type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; detail: CaseDetail };

const WORKSPACE_TABS = [
  { id: "documents", label: "Documents" },
  { id: "checks", label: "Vérifications" },
  { id: "activity", label: "Activité" },
  { id: "submission", label: "Soumission" },
];

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { config } = useSession();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [banner, setBanner] = useState<string | null>(null);

  function load(): void {
    if (!caseId) return;
    caseApi
      .getCase(caseId)
      .then((detail) => setState({ status: "loaded", detail }))
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : "Impossible de charger ce dossier.";
        setState({ status: "error", message });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when navigating to a different case
  }, [caseId]);

  async function handleSaveClaim(claim: Claim): Promise<IntakeFormResult> {
    if (state.status !== "loaded" || !caseId) return { ok: false, fieldErrors: [] };
    try {
      const result = await caseApi.updateClaim(caseId, state.detail.revision, claim);
      // B3: an optional semantic gate call can be re-triggered explicitly;
      // reflect whatever intake-check confirms as the current state.
      const intake = await caseApi.checkIntake(caseId, result.revision);
      setState({
        status: "loaded",
        detail: { ...state.detail, claim: result.claim, revision: result.revision, intake },
      });
      setBanner(null);
      return { ok: true };
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        setBanner("Le dossier a changé depuis votre dernière lecture. Vérifiez à nouveau les informations ci-dessous.");
        load();
        return { ok: false, fieldErrors: [] };
      }
      if (err instanceof ApiError) {
        return { ok: false, fieldErrors: err.fieldErrors, message: err.fieldErrors.length === 0 ? err.message : undefined };
      }
      return { ok: false, fieldErrors: [], message: "Une erreur inattendue s'est produite. Réessayez." };
    }
  }

  async function handleRetryGate(): Promise<void> {
    if (state.status !== "loaded" || !caseId) return;
    try {
      const intake = await caseApi.checkIntake(caseId, state.detail.revision);
      setState({ status: "loaded", detail: { ...state.detail, intake } });
    } catch {
      setBanner("La vérification reste indisponible pour le moment. Réessayez plus tard ou modifiez le dossier.");
    }
  }

  if (state.status === "loading") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="h-8 w-64 animate-pulse rounded-sm bg-surface-muted" />
        <div className="mt-4 h-32 animate-pulse rounded-md bg-surface-muted" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      </div>
    );
  }

  const { detail } = state;
  const notReady = detail.intake.status !== "ready";

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text">
            {detail.claim.claimant_name} <span className="text-text-subtle">c.</span> {detail.claim.counterparty_name}
          </h1>
          <p className="mt-1 text-xs text-text-muted">
            Révision <span className="tabular">{detail.revision}</span> · dossier{" "}
            <span className="tabular">{caseId}</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <p className="tabular text-md font-semibold text-text">
            {detail.claim.claimed_amount} {detail.claim.currency}
          </p>
          <Badge tone={INTAKE_STATUS_TONE[detail.intake.status]}>{INTAKE_STATUS_LABEL[detail.intake.status]}</Badge>
        </div>
      </div>

      {banner && (
        <p role="alert" className="mt-4 rounded-sm bg-warning-bg px-3 py-2 text-sm text-warning">
          {banner}
        </p>
      )}

      {notReady && config && (
        <div className="mt-6 rounded-md border border-border bg-surface p-6">
          <h2 className="text-md font-medium text-text">
            {detail.intake.status === "gate_unavailable"
              ? "Vérification indisponible"
              : "Plus de détails sont nécessaires"}
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            {detail.intake.status === "gate_unavailable"
              ? "La vérification n'a pas pu s'exécuter. Réessayez, ou modifiez le dossier ci-dessous."
              : "Complétez ou précisez les champs signalés ci-dessous, puis enregistrez pour poursuivre."}
          </p>
          {detail.intake.status === "gate_unavailable" && (
            <div className="mt-3">
              <Button variant="secondary" onClick={() => void handleRetryGate()}>
                Réessayer la vérification
              </Button>
            </div>
          )}
          <div className="mt-6">
            <IntakeForm
              config={config}
              initialClaim={detail.claim}
              questions={detail.intake.questions}
              submitLabel="Enregistrer"
              onSubmit={handleSaveClaim}
            />
          </div>
        </div>
      )}

      {!notReady && (
        <div className="mt-6">
          <Tabs
            idPrefix="case-workspace"
            tabs={WORKSPACE_TABS.map((tab) => ({
              ...tab,
              panel: (
                <p className="text-sm text-text-muted">
                  Cette section sera construite dans une prochaine étape.
                </p>
              ),
            }))}
          />
        </div>
      )}
    </div>
  );
}
