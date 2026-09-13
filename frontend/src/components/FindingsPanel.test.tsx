import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaseDetail, Job } from "../api/types";
import { STILL_PROCESSING_THRESHOLD_MS } from "../lib/useJobPolling";
import { FindingsPanel } from "./FindingsPanel";

vi.mock("../api", () => ({
  caseApi: { respondToFinding: vi.fn(), startAnalysis: vi.fn(), getJob: vi.fn() },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

function runningJob(overrides: Partial<Job> = {}): Job {
  return { id: "JOB_001", status: "running", phase: "reading", error: null, result_analysis_id: null, result_export_id: null, ...overrides };
}

/** Advances fake timers inside `act`, flushing the resulting getJob() promise and state update. */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function baseDetail(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return {
    case_id: "CASE_001",
    revision: 1,
    claim: {
      case_type: "unpaid_goods_invoice",
      claimant_name: "Amina",
      counterparty_name: "Client",
      claimed_amount: "20000.000",
      currency: "TND",
      dates: { contract: null, delivery: null, invoice: null, payment_due: null },
      requested_outcome: "payment",
      narrative: "…",
      follow_up_answers: [],
    },
    intake: { status: "ready", questions: [] },
    documents: [],
    latest_job: null,
    latest_analysis: null,
    submissions: [],
    activity: [],
    responses: [],
    ...overrides,
  };
}

describe("FindingsPanel", () => {
  beforeEach(() => {
    vi.mocked(caseApi.startAnalysis).mockReset();
    vi.mocked(caseApi.getJob).mockReset();
  });

  it("shows an honest empty state with a run trigger when no analysis has ever been published (UI-06)", () => {
    render(
      <FindingsPanel detail={baseDetail()} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />,
    );
    expect(screen.getByText(/Aucune analyse n'a encore été exécutée/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lancer l'analyse" })).toBeInTheDocument();
  });

  it("renders coverage counts, reconciliation as raw backend strings, and never a completeness percentage", () => {
    const detail = baseDetail({
      revision: 2,
      latest_analysis: {
        analysis_id: "RUN_001",
        case_id: "CASE_001",
        revision: 2,
        status: "ready",
        execution_mode: "fixture",
        checklist_version: "tn-goods-v1",
        legal_coverage: "unvalidated",
        coverage: { reviewed_pages: 5, unreadable_pages: 1, rejected_facts: 1 },
        checks: [],
        reconciliation: {
          documented_balance: "15000.000",
          currency: "TND",
          source_fact_ids: [],
          coverage_note: "Solde calculé à partir des pièces lisibles.",
        },
      },
    });
    render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);

    expect(screen.getByText("15000.000")).toBeInTheDocument();
    expect(screen.getByText(/Solde calculé à partir des pièces lisibles/)).toBeInTheDocument();
    expect(screen.getByText("Couverture juridique non validée")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows a clear banner and never a clean-looking dossier when the analysis is outdated (FE-04)", () => {
    const detail = baseDetail({
      revision: 3,
      latest_analysis: {
        analysis_id: "RUN_001",
        case_id: "CASE_001",
        revision: 2,
        status: "outdated",
        execution_mode: "fixture",
        checklist_version: "tn-goods-v1",
        legal_coverage: "unvalidated",
        coverage: { reviewed_pages: 5, unreadable_pages: 0, rejected_facts: 0 },
        checks: [],
        reconciliation: null,
      },
    });
    render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/réévaluation est requise/i);
  });

  it("filters findings by result without losing keyboard access", async () => {
    const user = userEvent.setup();
    const detail = baseDetail({
      latest_analysis: {
        analysis_id: "RUN_001",
        case_id: "CASE_001",
        revision: 1,
        status: "ready",
        execution_mode: "fixture",
        checklist_version: "tn-goods-v1",
        legal_coverage: "unvalidated",
        coverage: { reviewed_pages: 1, unreadable_pages: 0, rejected_facts: 0 },
        checks: [
          {
            check_id: "a",
            subject_id: "s1",
            subject_label: "Constat satisfait",
            finding_id: "finding_a",
            result: "satisfied",
            reason_code: "EVIDENCE_FOUND",
            finding_status: "resolved",
            delta: "resolved",
            basis: "checklist",
            message: "OK",
            evidence_refs: [],
            reviewed_document_ids: [],
            legal_reference_ids: [],
            actions: [],
          },
          {
            check_id: "b",
            subject_id: "s2",
            subject_label: "Constat contredit",
            finding_id: "finding_b",
            result: "contradicted",
            reason_code: "CONFLICT",
            finding_status: "open",
            delta: "new",
            basis: "reconciliation",
            message: "Écart détecté.",
            evidence_refs: [],
            reviewed_document_ids: [],
            legal_reference_ids: [],
            actions: ["disagree"],
          },
        ],
        reconciliation: null,
      },
    });
    render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);

    expect(screen.getByText("Constat satisfait")).toBeInTheDocument();
    expect(screen.getByText("Constat contredit")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Filtrer par résultat"), "contradicted");

    expect(screen.queryByText("Constat satisfait")).not.toBeInTheDocument();
    expect(screen.getByText("Constat contredit")).toBeInTheDocument();
  });

  it("shows a per-delta change-summary count alongside each finding's own delta badge", () => {
    const detail = baseDetail({
      latest_analysis: {
        analysis_id: "RUN_002",
        case_id: "CASE_001",
        revision: 1,
        status: "ready",
        execution_mode: "fixture",
        checklist_version: "tn-goods-v1",
        legal_coverage: "unvalidated",
        coverage: { reviewed_pages: 1, unreadable_pages: 0, rejected_facts: 0 },
        checks: [
          {
            check_id: "a",
            subject_id: "s1",
            subject_label: "Preuve de livraison",
            finding_id: "finding_a",
            result: "satisfied",
            reason_code: "EVIDENCE_FOUND",
            finding_status: "resolved",
            delta: "resolved",
            basis: "checklist",
            message: "OK",
            evidence_refs: [],
            reviewed_document_ids: [],
            legal_reference_ids: [],
            actions: [],
          },
          {
            check_id: "b",
            subject_id: "s2",
            subject_label: "Cohérence du montant",
            finding_id: "finding_b",
            result: "contradicted",
            reason_code: "CONFLICT",
            finding_status: "open",
            delta: "still_open",
            basis: "reconciliation",
            message: "Écart détecté.",
            evidence_refs: [],
            reviewed_document_ids: [],
            legal_reference_ids: [],
            actions: ["disagree"],
          },
        ],
        reconciliation: null,
      },
    });
    render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);

    expect(screen.getByText("Changements depuis la dernière analyse")).toBeInTheDocument();
    // Each finding keeps its own delta badge — never swapped between findings by position (FE-06).
    const deliveryCard = screen.getByText("Preuve de livraison").closest("li")!;
    expect(within(deliveryCard).getByText("Résolu depuis la dernière analyse")).toBeInTheDocument();
    const amountCard = screen.getByText("Cohérence du montant").closest("li")!;
    expect(within(amountCard).getByText("Toujours ouvert")).toBeInTheDocument();
  });

  describe("job polling (UI-06)", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("starts an analysis from the empty state and shows the running phases", async () => {
      vi.mocked(caseApi.startAnalysis).mockResolvedValueOnce({ job_id: "JOB_001", case_id: "CASE_001", revision: 1 });
      vi.mocked(caseApi.getJob).mockResolvedValue(runningJob({ phase: "extracting" }));

      render(<FindingsPanel detail={baseDetail()} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);

      // fireEvent (not userEvent) here: userEvent's own internal delays use
      // real timers even under `vi.useFakeTimers()`, which this test needs
      // for the subsequent phase/threshold assertions.
      fireEvent.click(screen.getByRole("button", { name: "Lancer l'analyse" }));
      await advance(0); // flush startAnalysis + the first getJob() poll

      expect(caseApi.startAnalysis).toHaveBeenCalledWith("CASE_001", 1, expect.any(String));
      expect(screen.getByRole("status")).toHaveTextContent(/Extraction des données/);
      // No double submit while a job is active: the trigger disappears.
      expect(screen.queryByRole("button", { name: "Lancer l'analyse" })).not.toBeInTheDocument();
    });

    it("resumes polling automatically when the case is reopened with an active job (frontend.md F4)", async () => {
      vi.mocked(caseApi.getJob).mockResolvedValue(runningJob());
      const detail = baseDetail({ latest_job: runningJob() });

      render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);
      await advance(0);

      expect(caseApi.getJob).toHaveBeenCalledWith("JOB_001");
      expect(screen.getByRole("status")).toHaveTextContent(/Analyse en cours/);
    });

    it("shows 'Toujours en cours de traitement' past the wait threshold without ever claiming a failure", async () => {
      vi.mocked(caseApi.getJob).mockResolvedValue(runningJob());
      const detail = baseDetail({ latest_job: runningJob() });

      render(<FindingsPanel detail={detail} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />);
      await advance(0);
      expect(caseApi.getJob).toHaveBeenCalledTimes(1);

      await advance(STILL_PROCESSING_THRESHOLD_MS + 5_000);

      expect(screen.getByText("Toujours en cours de traitement…")).toBeInTheDocument();
      expect(screen.queryByText(/a échoué/)).not.toBeInTheDocument();
    });
  });
});
