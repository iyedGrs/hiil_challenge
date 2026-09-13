import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import type { AppConfig, DocumentRecord } from "../api/types";
import { DocumentWorkspace } from "./DocumentWorkspace";

vi.mock("../api", () => ({
  caseApi: {
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getDocumentContentUrl: vi.fn(() => "/api/documents/x/content"),
    getDocumentPage: vi.fn(),
  },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

const CONFIG: AppConfig = {
  case_types: ["unpaid_goods_invoice"],
  currencies: ["TND"],
  requested_outcomes: ["payment"],
  limits: {
    max_active_files: 10,
    max_total_pages: 30,
    max_file_bytes: 10 * 1024 * 1024,
    max_case_bytes: 50 * 1024 * 1024,
    supported_mime_types: ["application/pdf", "image/jpeg", "image/png"],
  },
  legal_coverage: { unpaid_goods_invoice: "unvalidated" },
  execution_mode: "fixture",
};

function makeDoc(id: string): DocumentRecord {
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
  };
}

function renderWorkspace(documents: DocumentRecord[], onUpdate = vi.fn(), onReload = vi.fn()) {
  return render(
    <DocumentWorkspace
      caseId="CASE_001"
      revision={1}
      documents={documents}
      config={CONFIG}
      onUpdate={onUpdate}
      onReload={onReload}
      selectedDocumentId={null}
      selectedPage={1}
      onSelectDocument={vi.fn()}
      onSelectPage={vi.fn()}
    />,
  );
}

function pdfFile(name: string): File {
  return new File(["content"], name, { type: "application/pdf" });
}

async function selectFiles(container: HTMLElement, files: File[]): Promise<void> {
  const input = container.querySelector('input[type="file"][multiple]') as HTMLInputElement;
  await userEvent.upload(input, files);
}

describe("DocumentWorkspace upload queue", () => {
  it("shows the duplicate message without adding a new row", async () => {
    const existing = makeDoc("DOC_001");
    vi.mocked(caseApi.uploadDocument).mockResolvedValueOnce({ duplicate: true, document: existing, revision: 1 });
    const onUpdate = vi.fn();

    const { container } = renderWorkspace([existing], onUpdate);
    await selectFiles(container, [pdfFile("DOC_001.pdf")]);

    expect(await screen.findByText(/Ce fichier est déjà présent/)).toBeInTheDocument();
    expect(onUpdate).toHaveBeenCalledWith(1, [existing]);
  });

  it("stops the remaining queue and reloads the case on REVISION_CONFLICT", async () => {
    vi.mocked(caseApi.uploadDocument).mockRejectedValueOnce(
      new ApiError(409, { error: { code: "REVISION_CONFLICT", message: "Conflit.", field_errors: [], retryable: false } }),
    );
    const onReload = vi.fn();

    const { container } = renderWorkspace([], vi.fn(), onReload);
    await selectFiles(container, [pdfFile("a.pdf"), pdfFile("b.pdf")]);

    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
    expect(caseApi.uploadDocument).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Non envoyé — dossier rechargé/)).toBeInTheDocument();
  });
});
