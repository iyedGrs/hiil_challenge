import { ApiError } from "../ApiError";
import type { CaseApi } from "../CaseApi";
import type {
  Analysis,
  AppConfig,
  AuthSession,
  CaseDetail,
  CaseSummary,
  Claim,
  DocumentPage,
  DocumentRecord,
  FindingAction,
  FindingResponse,
  Intake,
  Job,
  ListResponse,
  Recipient,
  ReviewEvent,
  ReviewEventType,
  ReviewerSubmissionDetail,
  ReviewerSubmissionSummary,
  Submission,
} from "../types";
import { HttpClient, IDEMPOTENCY_HEADER } from "./client";

/** Real backend adapter — fetches relative `/api`, same interface as FixtureCaseApi. */
export class HttpCaseApi implements CaseApi {
  private readonly client = new HttpClient();

  async getConfig(): Promise<AppConfig> {
    return this.client.request<AppConfig>("/config");
  }

  async login(email: string, password: string): Promise<AuthSession> {
    const session = await this.client.request<AuthSession>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    this.client.setCsrfToken(session.csrf_token);
    return session;
  }

  async getCurrentUser(): Promise<AuthSession | null> {
    try {
      const session = await this.client.request<AuthSession>("/auth/me");
      this.client.setCsrfToken(session.csrf_token);
      return session;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  }

  async logout(): Promise<void> {
    await this.client.request<void>("/auth/logout", { method: "POST" });
    this.client.setCsrfToken(null);
  }

  async listCases(): Promise<ListResponse<CaseSummary>> {
    return this.client.request("/cases");
  }

  async createCase(claim: Claim): Promise<{ case_id: string; revision: number; intake: Intake }> {
    return this.client.request("/cases", { method: "POST", body: claim });
  }

  async getCase(caseId: string): Promise<CaseDetail> {
    return this.client.request(`/cases/${caseId}`);
  }

  async updateClaim(
    caseId: string,
    expectedRevision: number,
    claim: Claim,
  ): Promise<{ revision: number; intake: Intake; claim: Claim }> {
    return this.client.request(`/cases/${caseId}/claim`, {
      method: "PATCH",
      body: { expected_revision: expectedRevision, claim },
    });
  }

  async checkIntake(caseId: string, expectedRevision: number): Promise<Intake> {
    return this.client.request(`/cases/${caseId}/intake-check`, {
      method: "POST",
      body: { expected_revision: expectedRevision },
    });
  }

  async uploadDocument(
    caseId: string,
    expectedRevision: number,
    file: File,
  ): Promise<{ duplicate: boolean; document: DocumentRecord; revision: number }> {
    const form = new FormData();
    form.append("file", file);
    form.append("expected_revision", String(expectedRevision));
    return this.client.request(`/cases/${caseId}/documents`, { method: "POST", body: form });
  }

  async deleteDocument(caseId: string, documentId: string, expectedRevision: number): Promise<{ revision: number }> {
    return this.client.request(
      `/cases/${caseId}/documents/${documentId}?expected_revision=${expectedRevision}`,
      { method: "DELETE" },
    );
  }

  getDocumentContentUrl(documentId: string): string {
    return `/api/documents/${documentId}/content`;
  }

  async getDocumentPage(documentId: string, page: number): Promise<DocumentPage> {
    return this.client.request(`/documents/${documentId}/pages/${page}`);
  }

  async startAnalysis(
    caseId: string,
    expectedRevision: number,
    idempotencyKey: string,
  ): Promise<{ job_id: string; case_id: string; revision: number }> {
    return this.client.request(`/cases/${caseId}/analyses`, {
      method: "POST",
      body: { expected_revision: expectedRevision },
      headers: { [IDEMPOTENCY_HEADER]: idempotencyKey },
    });
  }

  async getJob(jobId: string): Promise<Job> {
    return this.client.request(`/jobs/${jobId}`);
  }

  async getAnalysis(analysisId: string): Promise<Analysis> {
    return this.client.request(`/analyses/${analysisId}`);
  }

  async respondToFinding(
    findingId: string,
    expectedRevision: number,
    action: FindingAction,
    explanation: string | null,
    documentIds: string[],
  ): Promise<{ revision: number; response: FindingResponse }> {
    return this.client.request(`/findings/${findingId}/responses`, {
      method: "POST",
      body: { expected_revision: expectedRevision, action, explanation, document_ids: documentIds },
    });
  }

  async listRecipients(): Promise<ListResponse<Recipient>> {
    return this.client.request("/recipients");
  }

  async createExport(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    acknowledgeUnresolved: boolean,
    idempotencyKey: string,
  ): Promise<{ job_id: string; export_id: string }> {
    return this.client.request(`/cases/${caseId}/exports`, {
      method: "POST",
      body: { expected_revision: expectedRevision, analysis_id: analysisId, acknowledge_unresolved: acknowledgeUnresolved },
      headers: { [IDEMPOTENCY_HEADER]: idempotencyKey },
    });
  }

  getExportContentUrl(exportId: string): string {
    return `/api/exports/${exportId}/content`;
  }

  async createSubmission(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    recipientId: string,
    acknowledgeUnresolved: boolean,
    idempotencyKey: string,
  ): Promise<Submission> {
    return this.client.request(`/cases/${caseId}/submissions`, {
      method: "POST",
      body: {
        expected_revision: expectedRevision,
        analysis_id: analysisId,
        recipient_id: recipientId,
        acknowledge_unresolved: acknowledgeUnresolved,
      },
      headers: { [IDEMPOTENCY_HEADER]: idempotencyKey },
    });
  }

  async listReviewerSubmissions(): Promise<ListResponse<ReviewerSubmissionSummary>> {
    return this.client.request("/reviewer/submissions");
  }

  async getReviewerSubmission(submissionId: string): Promise<ReviewerSubmissionDetail> {
    return this.client.request(`/reviewer/submissions/${submissionId}`);
  }

  async createReviewEvent(
    submissionId: string,
    eventType: ReviewEventType,
    message: string | null,
  ): Promise<ReviewEvent> {
    return this.client.request(`/reviewer/submissions/${submissionId}/events`, {
      method: "POST",
      body: { event_type: eventType, message },
    });
  }
}
