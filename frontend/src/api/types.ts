/**
 * Types for the B9 canonical API contract (spec/backend.md section B9).
 *
 * Conventions from B9: IDs are opaque strings; pages are 1-based; amounts are
 * decimal strings (never numbers); timestamps are UTC ISO 8601; document dates
 * are ISO dates or null; list responses use `{items, next_cursor}`; errors use
 * the envelope at the bottom of this file.
 *
 * Fields/shapes not literally spelled out in B9 are marked
 * `// PROVISIONAL (B9 gap): ...` and logged in spec/progress.md under
 * "B9 gaps (UI provisional types, pending API confirmation)".
 */

/** Generic paginated list response used by every B9 list route. */
export interface ListResponse<T> {
  items: T[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export type ExecutionMode = "fixture" | "live";

/** F5/B9 show only "unvalidated" for an in-progress pack; a validated state is implied. */
export type LegalCoverageStatus = "unvalidated" | "validated";

// PROVISIONAL (B9 gap): B9 names the `limits` field but not its inner shape.
// Field names below follow the local-dev.md L3 environment variable names.
export interface ConfigLimits {
  max_active_files: number;
  max_total_pages: number;
  max_file_bytes: number;
  max_case_bytes: number;
}

// PROVISIONAL (B9 gap): B9 names `legal_coverage` on /config but not its inner
// shape; modeled as a map of case type to coverage status.
export type ConfigLegalCoverage = Record<string, LegalCoverageStatus>;

export interface AppConfig {
  case_types: string[];
  currencies: string[];
  requested_outcomes: string[];
  limits: ConfigLimits;
  legal_coverage: ConfigLegalCoverage;
  execution_mode: ExecutionMode;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export type UserRole = "preparer" | "reviewer";

// PROVISIONAL (B9 gap): B9 names `user` but not its fields.
export interface AuthUser {
  id: string;
  email: string;
  role: UserRole;
  display_name: string;
}

export interface AuthSession {
  user: AuthUser;
  csrf_token: string;
}

// ---------------------------------------------------------------------------
// Claim / intake
// ---------------------------------------------------------------------------

export interface ClaimDates {
  contract: string | null;
  delivery: string | null;
  invoice: string | null;
  payment_due: string | null;
}

// PROVISIONAL (B9 gap): B9 documents follow_up_answers as "at most 5 answer
// objects, each bounded to 1000 characters and a server-issued question ID"
// but does not show the object's field names.
export interface FollowUpAnswer {
  question_id: string;
  answer: string;
}

/** Direct claim shape from B9's case-creation example; also nested under `claim` for PATCH. */
export interface Claim {
  case_type: string;
  claimant_name: string;
  counterparty_name: string;
  claimed_amount: string;
  currency: string;
  dates: ClaimDates;
  requested_outcome: string;
  narrative: string;
  follow_up_answers: FollowUpAnswer[];
}

export type IntakeStatus = "not_checked" | "ready" | "needs_information" | "gate_unavailable";

export interface IntakeQuestion {
  id: string;
  field: string;
  message: string;
}

export interface Intake {
  status: IntakeStatus;
  questions: IntakeQuestion[];
}

// PROVISIONAL (B9 gap): case list-summary fields are not enumerated by B9
// ("Authorized case summaries"); modeled as the fields the /cases screen (F4)
// needs to render a row.
export interface CaseSummary {
  case_id: string;
  case_type: string;
  claimant_name: string;
  counterparty_name: string;
  claimed_amount: string;
  currency: string;
  revision: number;
  intake_status: IntakeStatus;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

/** Required states per frontend.md F4. */
export type DocumentState = "uploaded" | "processing" | "ready" | "partial" | "unreadable" | "rejected";

// PROVISIONAL (B9 gap): the document object's fields beyond id are not
// enumerated by B9; modeled from frontend.md F4 ("filename, server document
// type, pages, upload time, reading state and errors").
export interface DocumentRecord {
  document_id: string;
  filename: string;
  document_type: string | null;
  pages: number | null;
  uploaded_at: string;
  state: DocumentState;
  error: string | null;
  active: boolean;
}

// PROVISIONAL (B9 gap): page preview/source-text response shape is not
// enumerated by B9 ("authorized page preview and source text/quality metadata").
export interface DocumentPage {
  document_id: string;
  page: number;
  image_url: string | null;
  source_text: string | null;
  method: "embedded_text" | "ocr" | null;
  quality: string | null;
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "superseded";

export type JobPhase =
  | "reading"
  | "extracting"
  | "validating_facts"
  | "checking"
  | "validating_checks"
  | "publishing"
  | "packaging";

export interface Job {
  id: string;
  status: JobStatus;
  phase: JobPhase | null;
  error: string | null;
  result_analysis_id: string | null;
  result_export_id: string | null;
}

// ---------------------------------------------------------------------------
// Analysis / findings
// ---------------------------------------------------------------------------

export type AnalysisStatus = "ready" | "partial" | "outdated";

export type CheckResult = "satisfied" | "contradicted" | "unassessable" | "not_applicable";

export type ReasonCode =
  | "EVIDENCE_FOUND"
  | "EVIDENCE_NOT_FOUND"
  | "CONFLICT"
  | "SOURCE_UNREADABLE"
  | "PARTIAL_COVERAGE"
  | "AMBIGUOUS_LINK"
  | "LEGAL_COVERAGE_UNAVAILABLE"
  | "INVALID_SOURCE"
  | "NOT_APPLICABLE";

export type FindingStatus = "open" | "resolved" | null;

export type FindingDelta = "new" | "resolved" | "still_open" | "reopened" | "not_applicable" | null;

/** Response actions per frontend.md F4 "Respond and reassess". */
export type FindingAction = "add_evidence" | "correct_claim" | "explain_unavailable" | "disagree";

/** Source basis per frontend.md F4 ("checklist, contract, claim or deterministic file/amount check"). */
export type FindingBasis = "checklist" | "contract" | "claim" | "deterministic";

export interface EvidenceRef {
  fact_id: string;
  document_id: string;
  page: number;
  source_text: string;
}

export interface CheckFinding {
  check_id: string;
  subject_id: string;
  finding_id: string;
  result: CheckResult;
  reason_code: ReasonCode;
  finding_status: FindingStatus;
  delta: FindingDelta;
  basis: FindingBasis;
  message: string;
  evidence_refs: EvidenceRef[];
  reviewed_document_ids: string[];
  legal_reference_ids: string[];
  actions: FindingAction[];
}

// PROVISIONAL (B9 gap): reconciliation fields beyond "decimal strings,
// currency, source fact IDs and a coverage qualification" are not enumerated.
export interface ReconciliationResult {
  documented_balance: string;
  currency: string;
  source_fact_ids: string[];
  coverage_note: string;
}

export interface AnalysisCoverage {
  reviewed_pages: number;
  unreadable_pages: number;
  rejected_facts: number;
}

export interface Analysis {
  analysis_id: string;
  case_id: string;
  revision: number;
  status: AnalysisStatus;
  execution_mode: ExecutionMode;
  checklist_version: string;
  legal_coverage: LegalCoverageStatus;
  coverage: AnalysisCoverage;
  checks: CheckFinding[];
  reconciliation: ReconciliationResult | null;
}

// PROVISIONAL (B9 gap): the saved finding-response object's fields are not
// enumerated ("saved response and revision").
export interface FindingResponse {
  finding_id: string;
  action: FindingAction;
  explanation: string | null;
  document_ids: string[];
  created_at: string;
}

// ---------------------------------------------------------------------------
// Case detail (composite)
// ---------------------------------------------------------------------------

// PROVISIONAL (B9 gap): case activity-log entry shape is not enumerated by B9
// ("... and activity").
export interface ActivityEvent {
  id: string;
  type: string;
  message: string;
  created_at: string;
}

// PROVISIONAL (B9 gap): submission-summary fields inside case detail are not
// enumerated by B9 ("submission summaries").
export interface SubmissionSummary {
  submission_id: string;
  revision: number;
  recipient_id: string;
  status: string;
  submitted_at: string;
}

// PROVISIONAL (B9 gap): the overall GET /cases/{id} composition is described
// in prose ("Claim, current revision, documents, latest analysis/job,
// submission summaries and activity") but not shown as JSON.
export interface CaseDetail {
  case_id: string;
  revision: number;
  claim: Claim;
  intake: Intake;
  documents: DocumentRecord[];
  latest_job: Job | null;
  latest_analysis: Analysis | null;
  submissions: SubmissionSummary[];
  activity: ActivityEvent[];
}

// ---------------------------------------------------------------------------
// Recipients / export / submission
// ---------------------------------------------------------------------------

// PROVISIONAL (B9 gap): recipient fields are not enumerated ("Available
// authorized reviewer destinations").
export interface Recipient {
  recipient_id: string;
  name: string;
}

/** States per frontend.md F4 ("Show actual states: generating, ready, failed."). */
export type ExportStatus = "generating" | "ready" | "failed";

// PROVISIONAL (B9 gap): export job object fields beyond job_id/export_id are
// not enumerated.
export interface ExportJob {
  export_id: string;
  status: ExportStatus;
}

// PROVISIONAL (B9 gap): submission object fields are not enumerated ("201
// submission").
export interface Submission {
  submission_id: string;
  case_id: string;
  revision: number;
  analysis_id: string;
  recipient_id: string;
  status: string;
  submitted_at: string;
}

// ---------------------------------------------------------------------------
// Reviewer back office
// ---------------------------------------------------------------------------

// PROVISIONAL (B9 gap): reviewer submission summary fields are not enumerated
// ("Assigned submission summaries").
export interface ReviewerSubmissionSummary {
  submission_id: string;
  case_id: string;
  claimant_name: string;
  status: string;
  submitted_at: string;
}

export type ReviewEventType = "received" | "clarification_requested" | "reviewed";

// PROVISIONAL (B9 gap): review event fields beyond event_type/message are not
// enumerated.
export interface ReviewEvent {
  event_id: string;
  event_type: ReviewEventType;
  message: string | null;
  created_at: string;
}

// PROVISIONAL (B9 gap): the immutable snapshot's overall composition is
// described in prose ("Immutable snapshot, documents, validated checks and
// events") but not shown as JSON.
export interface ReviewerSubmissionDetail {
  submission_id: string;
  case_id: string;
  revision: number;
  claim: Claim;
  documents: DocumentRecord[];
  analysis: Analysis;
  responses: FindingResponse[];
  events: ReviewEvent[];
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export interface FieldError {
  field: string;
  message: string;
}

/** Known error codes from B9; the union stays open for forward compatibility. */
export type ApiErrorCode =
  | "UNSUPPORTED_CASE_TYPE"
  | "INVALID_INPUT"
  | "FILE_LIMIT"
  | "UNSUPPORTED_FILE"
  | "REVISION_CONFLICT"
  | "INTAKE_NOT_READY"
  | "ANALYSIS_NOT_PUBLISHED"
  | "ANALYSIS_OUTDATED"
  | "ANALYSIS_ALREADY_RUNNING"
  | "BUDGET_EXHAUSTED"
  | "PROVIDER_UNAVAILABLE"
  | (string & {});

export interface ApiErrorBody {
  error: {
    code: ApiErrorCode;
    message: string;
    field_errors: FieldError[];
    retryable: boolean;
  };
}
