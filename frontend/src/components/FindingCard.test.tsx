import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import type { CheckFinding, DocumentRecord, FindingResponse } from "../api/types";
import { FindingCard } from "./FindingCard";

vi.mock("../api", () => ({
  caseApi: {
    respondToFinding: vi.fn(),
  },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

function makeDoc(id: string, overrides: Partial<DocumentRecord> = {}): DocumentRecord {
  return {
    document_id: id,
    filename: `${id}.pdf`,
    document_type: "invoice",
    pages: 1,
    uploaded_at: "2026-06-11T09:00:00Z",
    state: "ready",
    error: null,
    active: true,
    size_bytes: 1024,
    ...overrides,
  };
}

const FINDING: CheckFinding = {
  check_id: "delivery_evidence",
  subject_id: "invoice_0001",
  subject_label: "Preuve de livraison — facture n° 0001",
  finding_id: "finding_delivery_invoice_0001",
  result: "unassessable",
  reason_code: "EVIDENCE_NOT_FOUND",
  finding_status: "open",
  delta: "new",
  basis: "checklist",
  message: "Aucune preuve de réception trouvée dans les pièces examinées.",
  evidence_refs: [
    { fact_id: "fact_1", document_id: "DOC_001", page: 2, source_text: "Texte source cité." },
  ],
  reviewed_document_ids: ["DOC_001"],
  legal_reference_ids: [],
  actions: ["add_evidence", "explain_unavailable", "disagree"],
};

const DOCUMENTS = [makeDoc("DOC_001")];

function renderCard(overrides: Partial<React.ComponentProps<typeof FindingCard>> = {}) {
  const onRespond = vi.fn();
  const onRevisionConflict = vi.fn();
  const onOpenDocumentPage = vi.fn();
  const utils = render(
    <FindingCard
      finding={FINDING}
      revision={3}
      documents={DOCUMENTS}
      existingResponse={null}
      onRespond={onRespond}
      onRevisionConflict={onRevisionConflict}
      onOpenDocumentPage={onOpenDocumentPage}
      {...overrides}
    />,
  );
  return { ...utils, onRespond, onRevisionConflict, onOpenDocumentPage };
}

describe("FindingCard", () => {
  beforeEach(() => {
    vi.mocked(caseApi.respondToFinding).mockReset();
  });

  it("renders the finding by its stable finding_id, not by title or position", () => {
    renderCard();
    expect(screen.getByText(/finding_delivery_invoice_0001/)).toBeInTheDocument();
    expect(screen.getByText(FINDING.subject_label)).toBeInTheDocument();
    expect(screen.getByText(FINDING.message)).toBeInTheDocument();
  });

  it("opens the exact cited page through the deep-link callback (FE-05)", async () => {
    const user = userEvent.setup();
    const { onOpenDocumentPage } = renderCard();

    await user.click(screen.getByRole("button", { name: /page 2/i }));

    expect(onOpenDocumentPage).toHaveBeenCalledWith("DOC_001", 2);
  });

  it("escapes cited source text rather than rendering it as HTML", () => {
    const finding: CheckFinding = {
      ...FINDING,
      evidence_refs: [{ fact_id: "fact_1", document_id: "DOC_001", page: 1, source_text: "<b>injected</b>" }],
    };
    renderCard({ finding });
    expect(screen.getByText("<b>injected</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).not.toBeInTheDocument();
  });

  it("submits a response, applies the new revision, and states the finding is not resolved (FE-06)", async () => {
    const user = userEvent.setup();
    const savedResponse: FindingResponse = {
      finding_id: FINDING.finding_id,
      action: "disagree",
      explanation: "Je conteste ce constat.",
      document_ids: [],
      created_at: "2026-06-12T00:00:00Z",
    };
    vi.mocked(caseApi.respondToFinding).mockResolvedValueOnce({ revision: 4, response: savedResponse });
    const { onRespond } = renderCard();

    expect(screen.getByText(/prochaine analyse déterminera l'état/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Contester ce constat" }));
    await user.type(screen.getByLabelText(/Explication/), "Je conteste ce constat.");
    await user.click(screen.getByRole("button", { name: "Envoyer la réponse" }));

    expect(caseApi.respondToFinding).toHaveBeenCalledWith(
      FINDING.finding_id,
      3,
      "disagree",
      "Je conteste ce constat.",
      [],
    );
    expect(onRespond).toHaveBeenCalledWith(4, savedResponse);
  });

  it("reloads the case on REVISION_CONFLICT instead of applying a stale response", async () => {
    const user = userEvent.setup();
    vi.mocked(caseApi.respondToFinding).mockRejectedValueOnce(
      new ApiError(409, { error: { code: "REVISION_CONFLICT", message: "Conflit.", field_errors: [], retryable: false } }),
    );
    const { onRevisionConflict, onRespond } = renderCard();

    await user.click(screen.getByRole("button", { name: "Contester ce constat" }));
    await user.type(screen.getByLabelText(/Explication/), "Je conteste.");
    await user.click(screen.getByRole("button", { name: "Envoyer la réponse" }));

    expect(await screen.findByRole("button", { name: "Contester ce constat" })).toBeInTheDocument();
    expect(onRevisionConflict).toHaveBeenCalledTimes(1);
    expect(onRespond).not.toHaveBeenCalled();
  });

  it("shows the previous preparer response when one was already saved", () => {
    const existingResponse: FindingResponse = {
      finding_id: FINDING.finding_id,
      action: "explain_unavailable",
      explanation: "Ce document n'existe pas chez nous.",
      document_ids: [],
      created_at: "2026-06-12T00:00:00Z",
    };
    renderCard({ existingResponse });
    expect(screen.getByText("Ce document n'existe pas chez nous.")).toBeInTheDocument();
  });

  it("opens itself for an outstanding issue and collapses a settled check", async () => {
    const user = userEvent.setup();
    const { unmount } = renderCard();

    // `unassessable` is outstanding work, so the body is already readable.
    const issueHeader = screen.getByRole("button", { name: /Preuve de livraison/ });
    expect(issueHeader).toHaveAttribute("aria-expanded", "true");
    unmount();

    const settled = { ...FINDING, result: "satisfied", finding_status: "resolved", actions: [] } as CheckFinding;
    renderCard({ finding: settled });

    const settledHeader = screen.getByRole("button", { name: /Preuve de livraison/ });
    expect(settledHeader).toHaveAttribute("aria-expanded", "false");
    // The outcome still reads in the collapsed row.
    expect(screen.getByText(/Appuyé par les pièces/)).toBeInTheDocument();

    await user.click(settledHeader);
    expect(settledHeader).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(FINDING.message)).toBeVisible();
  });

  it("states the outcome once per card: result and status on one line, not three pills", () => {
    renderCard();
    const status = screen.getByText(/Non évaluable/);
    expect(status).toHaveTextContent("à traiter");
    // The old vocabulary rendered these as separate standalone badges.
    expect(screen.queryByText("Ouvert")).not.toBeInTheDocument();
    expect(screen.queryByText("Nouveau")).not.toBeInTheDocument();
  });

  it("requires selecting an owned document before submitting add_evidence", async () => {
    const user = userEvent.setup();
    renderCard();

    await user.click(screen.getByRole("button", { name: "Ajouter une pièce" }));
    await user.click(screen.getByRole("button", { name: "Envoyer la réponse" }));

    expect(screen.getByText(/Sélectionnez au moins un document/)).toBeInTheDocument();
    expect(caseApi.respondToFinding).not.toHaveBeenCalled();
  });
});
