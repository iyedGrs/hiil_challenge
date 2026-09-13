import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowClockwise,
  ArrowLeft,
  ClockCounterClockwise,
  Files,
  ListChecks,
  PaperPlaneTilt,
  Scales,
} from "@phosphor-icons/react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CaseDetail, Claim, DocumentRecord, FindingResponse } from "../api/types";
import { ActivityDrawer } from "../components/ActivityDrawer";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { CaseFlow, type FlowStep, type FlowStepState } from "../components/CaseFlow";
import { DocumentWorkspace } from "../components/DocumentWorkspace";
import { FindingsPanel } from "../components/FindingsPanel";
import { IntakeForm, type IntakeFormResult } from "../components/IntakeForm";
import { SubmissionPanel } from "../components/SubmissionPanel";
import { useToast } from "../components/Toast";
import { useSession } from "../session/SessionContext";
import { INTAKE_STATUS_LABEL } from "../lib/intakeStatus";
import { READINESS_LABEL, READINESS_TONE } from "../lib/findingLabels";
import { buildVerdict } from "../lib/verdict";

type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; detail: CaseDetail };

const STEP_IDS = ["claim", "documents", "checks", "submission"] as const;
type StepId = (typeof STEP_IDS)[number];

function isStepId(value: string | null): value is StepId {
  return value !== null && (STEP_IDS as readonly string[]).includes(value);
}

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { config } = useSession();
  const { notify } = useToast();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [banner, setBanner] = useState<string | null>(null);
  const [activityOpen, setActivityOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

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

  function goToStep(id: StepId): void {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", id);
      return next;
    });
  }

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
      if (intake.status === "ready") {
        notify("success", "Réclamation enregistrée. Vous pouvez passer aux pièces.");
      } else {
        notify("warning", "Réclamation enregistrée. Quelques précisions sont encore demandées ci-dessous.");
      }
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

  function updateDocuments(newRevision: number, documents: DocumentRecord[]): void {
    setState((prev) =>
      prev.status === "loaded" ? { status: "loaded", detail: { ...prev.detail, revision: newRevision, documents } } : prev,
    );
  }

  function selectDocument(documentId: string | null): void {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", "documents");
      if (documentId) {
        next.set("doc", documentId);
        next.set("page", "1");
      } else {
        next.delete("doc");
        next.delete("page");
      }
      return next;
    });
  }

  function selectPage(page: number): void {
    if (page < 1) return;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("page", String(page));
      return next;
    });
  }

  /** Citation deep link from a finding card into the Documents step (frontend.md FE-05). */
  function openDocumentPage(documentId: string, page: number): void {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", "documents");
      next.set("doc", documentId);
      next.set("page", String(page));
      return next;
    });
  }

  function handleFindingResponse(revision: number, response: FindingResponse): void {
    setState((prev) => {
      if (prev.status !== "loaded") return prev;
      const responses = [...prev.detail.responses.filter((r) => r.finding_id !== response.finding_id), response];
      return { status: "loaded", detail: { ...prev.detail, revision, responses } };
    });
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
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="skeleton h-8 w-64 rounded-sm" />
        <div className="skeleton mt-4 h-16 rounded-md" />
        <div className="skeleton mt-5 h-64 rounded-md" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      </div>
    );
  }

  const { detail } = state;
  const activeDocumentCount = detail.documents.filter((d) => d.active).length;
  const analysis = detail.latest_analysis;
  const verdict = analysis ? buildVerdict(analysis, detail.revision) : null;
  const intakeReady = detail.intake.status === "ready";

  const claimState: FlowStepState = intakeReady
    ? "done"
    : detail.intake.status === "not_checked"
      ? "todo"
      : "attention";

  const checksState: FlowStepState = !verdict
    ? "todo"
    : verdict.tone === "success"
      ? "done"
      : "attention";

  /*
   * The automatic readiness verdict gates transmission, so it drives that
   * step's own state in the rail instead of only appearing once the user has
   * arrived there.
   */
  const readiness = detail.readiness;
  const submissionState: FlowStepState =
    detail.submissions.length > 0
      ? "done"
      : readiness.status === "complete"
        ? "current"
        : readiness.status === "incomplete"
          ? "attention"
          : "todo";

  const steps: FlowStep[] = [
    {
      id: "claim",
      label: "Réclamation",
      hint: INTAKE_STATUS_LABEL[detail.intake.status],
      state: claimState,
      icon: Scales,
    },
    {
      id: "documents",
      label: "Pièces",
      hint: activeDocumentCount === 0 ? "Aucune pièce" : `${activeDocumentCount} pièce${activeDocumentCount > 1 ? "s" : ""}`,
      state: activeDocumentCount > 0 ? "done" : "todo",
      icon: Files,
    },
    {
      id: "checks",
      label: "Vérifications",
      hint: verdict ? verdict.headline : "Analyse non lancée",
      state: checksState,
      icon: ListChecks,
    },
    {
      id: "submission",
      label: "Transmission",
      hint:
        detail.submissions.length > 0
          ? `${detail.submissions.length} envoi${detail.submissions.length > 1 ? "s" : ""}`
          : readiness.status === "complete"
            ? "Prêt à transmettre"
            : READINESS_LABEL[readiness.status],
      state: submissionState,
      icon: PaperPlaneTilt,
    },
  ];

  const requestedStep = searchParams.get("tab");
  const activeStep: StepId = isStepId(requestedStep) ? requestedStep : intakeReady ? "documents" : "claim";

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <Link
        to="/cases"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-text-muted no-underline transition-colors hover:text-accent"
      >
        <ArrowLeft size={15} aria-hidden="true" />
        Mes dossiers
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl leading-tight font-semibold text-text" dir="auto">
            {detail.claim.claimant_name} <span className="font-normal text-text-subtle">c.</span>{" "}
            {detail.claim.counterparty_name}
          </h1>
          <p className="mt-1.5 text-xs text-text-muted">
            Révision <span className="tabular">{detail.revision}</span> · dossier{" "}
            <span className="tabular">{caseId}</span>
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <p className="tabular text-lg leading-none font-semibold tracking-tighter text-text">
            {detail.claim.claimed_amount} <span className="text-sm font-medium text-text-muted">{detail.claim.currency}</span>
          </p>
          <div className="flex items-center gap-2">
            {/*
             * The whole-case readiness verdict, not the intake gate: intake
             * state stays visible as the Réclamation step's own state in the
             * flow rail, so the header carries one status, not a stack.
             */}
            <Badge tone={READINESS_TONE[readiness.status]}>{READINESS_LABEL[readiness.status]}</Badge>
            <Button
              variant="ghost"
              size="sm"
              icon={<ClockCounterClockwise size={15} />}
              onClick={() => setActivityOpen(true)}
            >
              Historique
              {detail.activity.length > 0 && (
                <span className="tabular text-xs text-text-subtle">({detail.activity.length})</span>
              )}
            </Button>
          </div>
        </div>
      </div>

      <div className="mt-4">
        <Badge tone={READINESS_TONE[detail.readiness.status]}>{READINESS_LABEL[detail.readiness.status]}</Badge>
      </div>

      {banner && (
        <p role="alert" className="mt-4 rounded-sm bg-warning-bg px-3 py-2 text-sm text-warning">
          {banner}
        </p>
      )}

      <div className="mt-6">
        {config ? (
          <CaseFlow steps={steps} activeId={activeStep} onSelect={(id) => goToStep(id as StepId)}>
            {activeStep === "claim" && (
              <div className="flex flex-col gap-5">
                {!intakeReady && (
                  <div className="rounded-md border border-warning/40 bg-warning-bg p-4">
                    <h2 className="text-md font-semibold text-warning">
                      {detail.intake.status === "gate_unavailable"
                        ? "Vérification indisponible"
                        : "Plus de détails sont nécessaires"}
                    </h2>
                    <p className="mt-1 max-w-[65ch] text-sm text-warning">
                      {detail.intake.status === "gate_unavailable"
                        ? "La vérification n'a pas pu s'exécuter. Réessayez, ou modifiez le dossier ci-dessous."
                        : "Complétez ou précisez les champs signalés ci-dessous, puis enregistrez pour poursuivre."}
                    </p>
                    {detail.intake.status === "gate_unavailable" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<ArrowClockwise size={14} />}
                        className="mt-3"
                        onClick={() => void handleRetryGate()}
                      >
                        Réessayer la vérification
                      </Button>
                    )}
                  </div>
                )}

                <div className="rounded-md border border-border bg-surface p-5 shadow-raised">
                  <h2 className="text-md font-semibold text-text">Détails de la réclamation</h2>
                  <p className="mt-1 max-w-[65ch] text-sm text-text-muted">
                    Ces informations servent de référence à chaque vérification. Elles restent modifiables tant que le
                    dossier n'est pas transmis.
                  </p>
                  <div className="mt-5">
                    <IntakeForm
                      config={config}
                      initialClaim={detail.claim}
                      questions={detail.intake.questions}
                      submitLabel="Enregistrer"
                      onSubmit={handleSaveClaim}
                    />
                  </div>
                </div>
              </div>
            )}

            {activeStep === "documents" && caseId && (
              <DocumentWorkspace
                caseId={caseId}
                revision={detail.revision}
                documents={detail.documents}
                config={config}
                onUpdate={updateDocuments}
                onReload={load}
                selectedDocumentId={searchParams.get("doc")}
                selectedPage={Number(searchParams.get("page") ?? "1") || 1}
                onSelectDocument={selectDocument}
                onSelectPage={selectPage}
              />
            )}

            {activeStep === "checks" && caseId && (
              <FindingsPanel
                detail={detail}
                onUpdate={handleFindingResponse}
                onReload={load}
                onOpenDocumentPage={openDocumentPage}
                onNavigateToSubmission={() => goToStep("submission")}
              />
            )}

            {activeStep === "submission" && caseId && (
              <SubmissionPanel
                caseId={caseId}
                detail={detail}
                onReload={load}
                onNavigateToChecks={() => goToStep("checks")}
              />
            )}
          </CaseFlow>
        ) : (
          <div className="skeleton h-64 rounded-md" />
        )}
      </div>

      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} activity={detail.activity} />
    </div>
  );
}
