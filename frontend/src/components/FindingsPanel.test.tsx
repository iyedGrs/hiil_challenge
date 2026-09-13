import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CaseDetail } from "../api/types";
import { FindingsPanel } from "./FindingsPanel";

vi.mock("../api", () => ({
  caseApi: { respondToFinding: vi.fn() },
}));

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
  it("shows an honest empty state without a run button when no analysis has ever been published", () => {
    render(
      <FindingsPanel detail={baseDetail()} onUpdate={vi.fn()} onReload={vi.fn()} onOpenDocumentPage={vi.fn()} />,
    );
    expect(screen.getByText(/Aucune analyse n'a encore été exécutée/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /lancer|démarrer/i })).not.toBeInTheDocument();
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
            basis: "deterministic",
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
});
