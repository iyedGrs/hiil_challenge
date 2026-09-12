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
} from "./types";

/**
 * One interface, one method per B9 route (health excluded — it is an
 * infrastructure check, not a case-preparation operation). Fixture and HTTP
 * adapters both implement this; `VITE_DATA_MODE` picks which one is used
 * (see ./index.ts).
 */
export interface CaseApi {
  getConfig(): Promise<AppConfig>;

  login(email: string, password: string): Promise<AuthSession>;
  /** Restores a session from the server cookie; null when unauthenticated (no throw on 401). */
  getCurrentUser(): Promise<AuthSession | null>;
  logout(): Promise<void>;

  listCases(): Promise<ListResponse<CaseSummary>>;
  createCase(claim: Claim): Promise<{ case_id: string; revision: number; intake: Intake }>;
  getCase(caseId: string): Promise<CaseDetail>;
  updateClaim(
    caseId: string,
    expectedRevision: number,
    claim: Claim,
  ): Promise<{ revision: number; intake: Intake; claim: Claim }>;
  checkIntake(caseId: string, expectedRevision: number): Promise<Intake>;

  uploadDocument(
    caseId: string,
    expectedRevision: number,
    file: File,
  ): Promise<{ duplicate: boolean; document: DocumentRecord; revision: number }>;
  deleteDocument(caseId: string, documentId: string, expectedRevision: number): Promise<{ revision: number }>;
  /** Authorized-download URL; the browser sends session cookies same-origin. */
  getDocumentContentUrl(documentId: string): string;
  getDocumentPage(documentId: string, page: number): Promise<DocumentPage>;

  startAnalysis(
    caseId: string,
    expectedRevision: number,
    idempotencyKey: string,
  ): Promise<{ job_id: string; case_id: string; revision: number }>;
  getJob(jobId: string): Promise<Job>;
  getAnalysis(analysisId: string): Promise<Analysis>;

  respondToFinding(
    findingId: string,
    expectedRevision: number,
    action: FindingAction,
    explanation: string | null,
    documentIds: string[],
  ): Promise<{ revision: number; response: FindingResponse }>;

  listRecipients(): Promise<ListResponse<Recipient>>;

  createExport(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    acknowledgeUnresolved: boolean,
    idempotencyKey: string,
  ): Promise<{ job_id: string; export_id: string }>;
  getExportContentUrl(exportId: string): string;

  createSubmission(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    recipientId: string,
    acknowledgeUnresolved: boolean,
    idempotencyKey: string,
  ): Promise<Submission>;

  listReviewerSubmissions(): Promise<ListResponse<ReviewerSubmissionSummary>>;
  getReviewerSubmission(submissionId: string): Promise<ReviewerSubmissionDetail>;
  createReviewEvent(
    submissionId: string,
    eventType: ReviewEventType,
    message: string | null,
  ): Promise<ReviewEvent>;
}
