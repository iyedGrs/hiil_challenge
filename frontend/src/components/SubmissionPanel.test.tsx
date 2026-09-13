import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import type { Analysis, CaseDetail, Job, Recipient, Submission } from "../api/types";
import { SubmissionPanel } from "./SubmissionPanel";

vi.mock("../api", () => ({
  caseApi: {
    listRecipients: vi.fn(),
    createExport: vi.fn(),
    createSubmission: vi.fn(),
    getExportContentUrl: vi.fn((id: string) => `https://example.test/exports/${id}`),
    getJob: vi.fn(),
  },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

const RECIPIENTS: Recipient[] = [{ recipient_id: "recipient_1", name: "Réviseur Démo", remit: "Reviews submitted case packages." }];

function baseAnalysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    analysis_id: "RUN_001",
    case_id: "CASE_001",
    revision: 1,
    status: "ready",
    execution_mode: "fixture",
    checklist_version: "tn-goods-v1",
    legal_coverage: "unvalidated",
    coverage: { reviewed_pages: 5, unreadable_pages: 0, rejected_facts: 0 },
    checks: [],
    reconciliation: null,
    ...overrides,
  };
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
    latest_analysis: baseAnalysis(),
    submissions: [],
    activity: [],
    responses: [],
    ...overrides,
  };
}

async function selectRecipientAndConfirm(): Promise<void> {
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText("Destinataire"), "recipient_1");
  await user.click(screen.getByRole("checkbox", { name: /Je confirme la transmission/ }));
}

describe("SubmissionPanel", () => {
  beforeEach(() => {
    vi.mocked(caseApi.listRecipients).mockReset().mockResolvedValue({ items: RECIPIENTS, next_cursor: null });
    vi.mocked(caseApi.createExport).mockReset();
    vi.mocked(caseApi.createSubmission).mockReset();
    vi.mocked(caseApi.getJob).mockReset();
  });

  it("blocks submission when the analysis is outdated (frontend.md FE-04)", async () => {
    const detail = baseDetail({ revision: 3, latest_analysis: baseAnalysis({ revision: 2, status: "ready" }) });
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/révision antérieure/i);
    await selectRecipientAndConfirm();
    expect(screen.getByRole("button", { name: "Transmettre" })).toBeDisabled();
  });

  it("blocks submission when the latest job failed", async () => {
    const detail = baseDetail({
      latest_job: { id: "JOB_1", status: "failed", phase: null, error: "boom", result_analysis_id: null, result_export_id: null },
    });
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/dernière tentative d'analyse a échoué/i);
    await selectRecipientAndConfirm();
    expect(screen.getByRole("button", { name: "Transmettre" })).toBeDisabled();
  });

  it("requires an explicit acknowledgement checkbox before a partial analysis can be submitted", async () => {
    const detail = baseDetail({ latest_analysis: baseAnalysis({ status: "partial" }) });
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={vi.fn()} />);

    await selectRecipientAndConfirm();
    expect(screen.getByRole("button", { name: "Transmettre" })).toBeDisabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: /analyse est partielle/i }));
    expect(screen.getByRole("button", { name: "Transmettre" })).toBeEnabled();
  });

  it("shows the confirmation text and submission ID on a successful submit", async () => {
    const submission: Submission = {
      submission_id: "SUB_001",
      case_id: "CASE_001",
      revision: 1,
      analysis_id: "RUN_001",
      recipient_id: "recipient_1",
      status: "submitted",
      submitted_at: "2026-09-13T10:00:00Z",
    };
    vi.mocked(caseApi.createSubmission).mockResolvedValueOnce(submission);
    const detail = baseDetail();
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={vi.fn()} />);

    await selectRecipientAndConfirm();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Transmettre" }));

    expect(await screen.findByText("Transmis pour examen sur la plateforme")).toBeInTheDocument();
    expect(screen.getByText(/SUB_001/)).toBeInTheDocument();
    expect(screen.queryByText(/Déposé au tribunal/)).not.toBeInTheDocument();
  });

  it("reloads the case and resets confirmation on REVISION_CONFLICT", async () => {
    vi.mocked(caseApi.createSubmission).mockRejectedValueOnce(
      new ApiError(409, { error: { code: "REVISION_CONFLICT", message: "stale", field_errors: [], retryable: false } }),
    );
    const onReload = vi.fn();
    const detail = baseDetail();
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={onReload} onNavigateToChecks={vi.fn()} />);

    await selectRecipientAndConfirm();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Transmettre" }));

    expect(await screen.findByText("Le dossier a changé, vérifiez-le à nouveau")).toBeInTheDocument();
    expect(onReload).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("checkbox", { name: /Je confirme la transmission/ })).not.toBeChecked();
  });

  it("shows the download link once the export job succeeds", async () => {
    vi.mocked(caseApi.createExport).mockResolvedValueOnce({ job_id: "JOB_EXPORT", export_id: "EXPORT_1" });
    const succeededJob: Job = {
      id: "JOB_EXPORT",
      status: "succeeded",
      phase: "packaging",
      error: null,
      result_analysis_id: "RUN_001",
      result_export_id: "EXPORT_1",
    };
    vi.mocked(caseApi.getJob).mockResolvedValue(succeededJob);
    const detail = baseDetail();
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={vi.fn()} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Générer le dossier" }));

    expect(await screen.findByRole("link", { name: "Télécharger le dossier" })).toHaveAttribute(
      "href",
      "https://example.test/exports/EXPORT_1",
    );
  });

  it("waits for reassessment via the Vérifications tab link when blocked", async () => {
    const onNavigateToChecks = vi.fn();
    const detail = baseDetail({ latest_analysis: null });
    render(<SubmissionPanel caseId="CASE_001" detail={detail} onReload={vi.fn()} onNavigateToChecks={onNavigateToChecks} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Aller à Vérifications" }));
    expect(onNavigateToChecks).toHaveBeenCalledTimes(1);
  });
});
