import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ReviewerSubmissionSummary } from "../api/types";
import { ReviewerSubmissionsPage } from "./ReviewerSubmissionsPage";

vi.mock("../api", () => ({
  caseApi: { listReviewerSubmissions: vi.fn() },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

const SUBMISSION: ReviewerSubmissionSummary = {
  submission_id: "SUB_001",
  case_id: "CASE_001",
  claimant_name: "Amina Gharbi",
  revision: 3,
  status: "submitted",
  submitted_at: "2026-06-12T09:00:00Z",
  readiness: { status: "complete", reasons: [] },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ReviewerSubmissionsPage />
    </MemoryRouter>,
  );
}

describe("ReviewerSubmissionsPage", () => {
  it("lists an assigned submission with claimant, case, revision and status, linking to its detail page", async () => {
    vi.mocked(caseApi.listReviewerSubmissions).mockResolvedValueOnce({ items: [SUBMISSION], next_cursor: null });
    renderPage();

    expect(await screen.findByText("Amina Gharbi")).toBeInTheDocument();
    const meta = screen.getByText(/CASE_001/).closest("p");
    expect(meta).toHaveTextContent("CASE_001");
    expect(meta).toHaveTextContent(/révision\s*3/);
    expect(screen.getByText("Soumis")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/reviewer/submissions/SUB_001");
  });

  it("shows an empty state when nothing is assigned", async () => {
    vi.mocked(caseApi.listReviewerSubmissions).mockResolvedValueOnce({ items: [], next_cursor: null });
    renderPage();

    expect(await screen.findByText(/Aucun dossier ne vous a été assigné/)).toBeInTheDocument();
  });
});
