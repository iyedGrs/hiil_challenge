import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DocumentRecord } from "../api/types";
import { DocumentPreview } from "./DocumentPreview";

vi.mock("../api", () => ({
  caseApi: {
    getDocumentPage: vi.fn().mockResolvedValue({
      document_id: "DOC_005",
      page: 1,
      image_url: null,
      source_text: "نطالب بتسوية باقي المستحقات المتعلقة بالفاتورة رقم 0001",
      method: "ocr",
      quality: "bonne",
    }),
    getDocumentContentUrl: vi.fn(() => "/api/documents/DOC_005/content"),
  },
}));

const DOC: DocumentRecord = {
  document_id: "DOC_005",
  filename: "lettre_reclamation_ar.pdf",
  document_type: "correspondence",
  pages: 1,
  uploaded_at: "2026-06-11T09:08:00Z",
  state: "ready",
  error: null,
  active: true,
  size_bytes: 154_760,
};

describe("DocumentPreview", () => {
  it("renders Arabic source text as escaped text inside a dir=auto element", async () => {
    render(<DocumentPreview document={DOC} page={1} onPageChange={vi.fn()} />);

    const sourceText = await screen.findByText(/نطالب بتسوية/);
    expect(sourceText.tagName).toBe("PRE");
    expect(sourceText.getAttribute("dir")).toBe("auto");
    // Rendered as React text (never dangerouslySetInnerHTML) — no markup leaks through.
    expect(sourceText.innerHTML).not.toContain("<");
  });
});
