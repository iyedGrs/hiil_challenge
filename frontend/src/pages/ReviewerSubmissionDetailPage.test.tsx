import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import type { ReviewerSubmissionDetail, ReviewEvent } from "../api/types";
import { ReviewerSubmissionDetailPage } from "./ReviewerSubmissionDetailPage";

vi.mock("../api", () => ({
  caseApi: {
    getReviewerSubmission: vi.fn(),
    createReviewEvent: vi.fn(),
    getDocumentPage: vi.fn(),
    getDocumentContentUrl: vi.fn(() => "/api/documents/x/content"),
  },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

function baseDetail(overrides: Partial<ReviewerSubmissionDetail> = {}): ReviewerSubmissionDetail {
  return {
    submission_id: "SUB_001",
    case_id: "CASE_001",
    revision: 3,
    claim: {
      case_type: "unpaid_goods_invoice",
      claimant_name: "Amina Gharbi",
      counterparty_name: "Client Démo SARL",
      claimed_amount: "20000.000",
      currency: "TND",
      dates: { contract: null, delivery: null, invoice: null, payment_due: null },
      requested_outcome: "payment",
      narrative: "Nous avons fourni du mobilier de bureau à ce client.",
      follow_up_answers: [],
    },
    documents: [
      {
        document_id: "DOC_001",
        filename: "facture_0001.pdf",
        document_type: "invoice",
        pages: 1,
        uploaded_at: "2026-06-11T09:00:00Z",
        state: "ready",
        error: null,
        active: true,
        size_bytes: 1024,
      },
    ],
    analysis: {
      analysis_id: "RUN_001",
      case_id: "CASE_001",
      revision: 3,
      status: "ready",
      execution_mode: "fixture",
      checklist_version: "tn-goods-v1",
      legal_coverage: "unvalidated",
      coverage: { reviewed_pages: 5, unreadable_pages: 1, rejected_facts: 1 },
      checks: [
        {
          check_id: "delivery_evidence",
          subject_id: "invoice_0001",
          subject_label: "Preuve de livraison",
          finding_id: "finding_delivery_invoice_0001",
          result: "unassessable",
          reason_code: "EVIDENCE_NOT_FOUND",
          finding_status: "open",
          delta: null,
          basis: "checklist",
          message: "Aucune preuve de réception trouvée.",
          evidence_refs: [],
          reviewed_document_ids: ["DOC_001"],
          legal_reference_ids: [],
          actions: ["add_evidence", "explain_unavailable", "disagree"],
        },
      ],
      reconciliation: null,
    },
    readiness: { status: "complete", reasons: [] },
    responses: [],
    events: [],
    ...overrides,
  };
}

function renderPage(submissionId = "SUB_001") {
  return render(
    <MemoryRouter initialEntries={[`/reviewer/submissions/${submissionId}`]}>
      <Routes>
        <Route path="/reviewer/submissions/:submissionId" element={<ReviewerSubmissionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ReviewerSubmissionDetailPage", () => {
  it("shows the frozen snapshot: claim, documents, validated checks and limitations, without a response form", async () => {
    vi.mocked(caseApi.getReviewerSubmission).mockResolvedValueOnce(baseDetail());
    vi.mocked(caseApi.getDocumentPage).mockResolvedValue({
      document_id: "DOC_001",
      page: 1,
      image_url: null,
      source_text: "Facture n° 0001.",
      method: "embedded_text",
      quality: "bonne",
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: /Amina Gharbi/ })).toBeInTheDocument();
    expect(screen.getAllByText("facture_0001.pdf").length).toBeGreaterThan(0);
    expect(screen.getByText("Preuve de livraison")).toBeInTheDocument();
    expect(screen.getByText(/Non évaluable/)).toBeInTheDocument();
    // A reviewer never gets the respond-to-finding controls.
    expect(screen.queryByRole("button", { name: "Ajouter une pièce" })).not.toBeInTheDocument();
    // Received/reviewed must not read as legal acceptance.
    expect(screen.getByText(/n'emporte aucune acceptation/)).toBeInTheDocument();
    // The frozen readiness verdict is shown, not decided by the reviewer.
    expect(screen.getByText("Dossier complet et cohérent – prêt à transmettre")).toBeInTheDocument();
  });

  it("is a read-only inbox: no action to mark received/reviewed or request clarification", async () => {
    vi.mocked(caseApi.getReviewerSubmission).mockResolvedValueOnce(baseDetail());
    renderPage();
    await screen.findAllByText("facture_0001.pdf");

    expect(screen.queryByRole("button", { name: "Marquer comme reçu" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Marquer comme examiné" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Demander une clarification")).not.toBeInTheDocument();
    expect(caseApi.createReviewEvent).not.toHaveBeenCalled();
  });

  it("still shows prior reviewer events as read-only history", async () => {
    const event: ReviewEvent = {
      event_id: "EVT_001",
      event_type: "clarification_requested",
      message: "Merci de préciser la date de livraison.",
      created_at: "2026-06-13T10:00:00Z",
    };
    vi.mocked(caseApi.getReviewerSubmission).mockResolvedValueOnce(baseDetail({ events: [event] }));

    renderPage();

    expect(await screen.findByText(/Merci de préciser la date de livraison\./)).toBeInTheDocument();
  });

  it("shows an honest not-found state for an unknown or unassigned submission", async () => {
    vi.mocked(caseApi.getReviewerSubmission).mockRejectedValueOnce(
      new ApiError(404, { error: { code: "NOT_FOUND", message: "Ressource introuvable.", field_errors: [], retryable: false } }),
    );
    renderPage("SUB_UNKNOWN");

    expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable ou n'est pas autorisé/);
  });
});
