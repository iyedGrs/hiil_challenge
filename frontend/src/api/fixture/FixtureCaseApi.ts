import { ApiError } from "../ApiError";
import type { CaseApi } from "../CaseApi";
import type {
  Analysis,
  AppConfig,
  AuthSession,
  AuthUser,
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
import { FIXTURE_CONFIG, FIXTURE_RECIPIENTS, FIXTURE_USERS } from "./seed";
import { createFixtureStore, type FixtureStore, type StoredCase } from "./store";

function unauthenticated(): ApiError {
  return new ApiError(401, {
    error: { code: "UNAUTHENTICATED", message: "Authentification requise.", field_errors: [], retryable: false },
  });
}

function notFound(): ApiError {
  // B9: use 404 for inaccessible case resources rather than disclosing existence.
  return new ApiError(404, {
    error: { code: "NOT_FOUND", message: "Ressource introuvable.", field_errors: [], retryable: false },
  });
}

function revisionConflict(): ApiError {
  return new ApiError(409, {
    error: {
      code: "REVISION_CONFLICT",
      message: "Le dossier a changé depuis votre dernière lecture. Rechargez et réessayez.",
      field_errors: [],
      retryable: false,
    },
  });
}

function intakeNotReady(intake: Intake): ApiError {
  return new ApiError(409, {
    error: {
      code: "INTAKE_NOT_READY",
      message: "Des informations complémentaires sont nécessaires avant de lancer l'analyse.",
      field_errors: intake.questions.map((q) => ({ field: q.field, message: q.message })),
      retryable: false,
    },
  });
}

function toAuthUser(user: AuthUser): AuthUser {
  const { id, email, role, display_name } = user;
  return { id, email, role, display_name };
}

/** Matches a mention of the supplied goods/merchandise in French narrative text. */
const GOODS_MENTION = /\bbiens?\b|\bmarchandises?\b|\bmatériel\b|\bfournitures?\b|\bproduits?\b/i;

/**
 * Cheap deterministic gate — no model call, matching B3 for fixture mode.
 * Deterministic and consistent so the same claim always yields the same
 * result: a narrative that never mentions the supplied goods stays
 * `needs_information` until either the narrative is edited to mention them
 * or the mapped follow-up question is answered (frontend.md F4/F5).
 */
function evaluateIntake(claim: Claim): Intake {
  const narrative = claim.narrative.trim();
  if (narrative.length < 30) {
    return {
      status: "needs_information",
      questions: [
        {
          id: "narrative_too_short",
          field: "narrative",
          message: "Merci de décrire la transaction plus précisément (30 caractères minimum).",
        },
      ],
    };
  }

  const answeredGoods = claim.follow_up_answers.some(
    (a) => a.question_id === "describe_goods" && a.answer.trim().length > 0,
  );
  if (!GOODS_MENTION.test(narrative) && !answeredGoods) {
    return {
      status: "needs_information",
      questions: [{ id: "describe_goods", field: "narrative", message: "Quels biens ont été fournis ?" }],
    };
  }

  return { status: "ready", questions: [] };
}

function toCaseSummary(c: StoredCase): CaseSummary {
  return {
    case_id: c.case_id,
    case_type: c.claim.case_type,
    claimant_name: c.claim.claimant_name,
    counterparty_name: c.claim.counterparty_name,
    claimed_amount: c.claim.claimed_amount,
    currency: c.claim.currency,
    revision: c.revision,
    intake_status: c.intake.status,
    updated_at: new Date().toISOString(),
  };
}

function toCaseDetail(c: StoredCase): CaseDetail {
  const latestJob = c.jobs.at(-1) ?? null;
  const latestAnalysis = c.analyses.at(-1) ?? null;
  return {
    case_id: c.case_id,
    revision: c.revision,
    claim: structuredClone(c.claim),
    intake: structuredClone(c.intake),
    documents: structuredClone(c.documents),
    latest_job: latestJob ? structuredClone(latestJob) : null,
    latest_analysis: latestAnalysis ? structuredClone(latestAnalysis) : null,
    submissions: structuredClone(c.submissions),
    activity: structuredClone(c.activity),
  };
}

/**
 * In-memory fixture adapter. Visibly demo-only (see the app-shell banner,
 * FE-12) and never presents seeded data as a live AI result. Each instance
 * owns its own store — construct one per app lifetime (see ../index.ts).
 */
export class FixtureCaseApi implements CaseApi {
  private readonly store: FixtureStore = createFixtureStore();

  private requireAuth(): AuthUser {
    const user = FIXTURE_USERS.find((u) => u.id === this.store.currentUserId);
    if (!user) throw unauthenticated();
    return user;
  }

  private requireCase(caseId: string): StoredCase {
    const user = this.requireAuth();
    const record = this.store.cases.get(caseId);
    if (!record || record.owner_id !== user.id) throw notFound();
    return record;
  }

  private requireRevision(record: StoredCase, expectedRevision: number): void {
    if (record.revision !== expectedRevision) throw revisionConflict();
  }

  async getConfig(): Promise<AppConfig> {
    return structuredClone(FIXTURE_CONFIG);
  }

  async login(email: string, password: string): Promise<AuthSession> {
    const user = FIXTURE_USERS.find((u) => u.email === email && u.password === password);
    if (!user) {
      throw new ApiError(401, {
        error: { code: "UNAUTHENTICATED", message: "Identifiants invalides.", field_errors: [], retryable: false },
      });
    }
    this.store.currentUserId = user.id;
    return { user: toAuthUser(user), csrf_token: "fixture-csrf-token" };
  }

  async getCurrentUser(): Promise<AuthSession | null> {
    const user = FIXTURE_USERS.find((u) => u.id === this.store.currentUserId);
    if (!user) return null;
    return { user: toAuthUser(user), csrf_token: "fixture-csrf-token" };
  }

  async logout(): Promise<void> {
    this.store.currentUserId = null;
  }

  async listCases(): Promise<ListResponse<CaseSummary>> {
    const user = this.requireAuth();
    const items = [...this.store.cases.values()].filter((c) => c.owner_id === user.id).map(toCaseSummary);
    return { items, next_cursor: null };
  }

  async createCase(claim: Claim): Promise<{ case_id: string; revision: number; intake: Intake }> {
    const user = this.requireAuth();
    if (!FIXTURE_CONFIG.case_types.includes(claim.case_type)) {
      throw new ApiError(422, {
        error: {
          code: "UNSUPPORTED_CASE_TYPE",
          message: "Type de dossier non pris en charge.",
          field_errors: [{ field: "case_type", message: "Type de dossier non pris en charge." }],
          retryable: false,
        },
      });
    }
    const case_id = this.store.nextId("CASE");
    const intake = evaluateIntake(claim);
    const record: StoredCase = {
      case_id,
      owner_id: user.id,
      claim: structuredClone(claim),
      revision: 1,
      intake,
      documents: [],
      analyses: [],
      jobs: [],
      submissions: [],
      activity: [],
      responses: {},
    };
    this.store.cases.set(case_id, record);
    return { case_id, revision: record.revision, intake: structuredClone(intake) };
  }

  async getCase(caseId: string): Promise<CaseDetail> {
    return toCaseDetail(this.requireCase(caseId));
  }

  async updateClaim(
    caseId: string,
    expectedRevision: number,
    claim: Claim,
  ): Promise<{ revision: number; intake: Intake; claim: Claim }> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    record.claim = structuredClone(claim);
    record.revision += 1;
    record.intake = evaluateIntake(record.claim);
    return { revision: record.revision, intake: structuredClone(record.intake), claim: structuredClone(record.claim) };
  }

  async checkIntake(caseId: string, expectedRevision: number): Promise<Intake> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    return structuredClone(record.intake);
  }

  async uploadDocument(
    caseId: string,
    expectedRevision: number,
    file: File,
  ): Promise<{ duplicate: boolean; document: DocumentRecord; revision: number }> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);

    const existing = record.documents.find((d) => d.active && d.filename === file.name);
    if (existing) {
      return { duplicate: true, document: structuredClone(existing), revision: record.revision };
    }

    if (record.documents.filter((d) => d.active).length >= FIXTURE_CONFIG.limits.max_active_files) {
      throw new ApiError(413, {
        error: { code: "FILE_LIMIT", message: "Nombre maximal de fichiers atteint.", field_errors: [], retryable: false },
      });
    }

    const document: DocumentRecord = {
      document_id: this.store.nextId("DOC"),
      filename: file.name,
      document_type: null,
      pages: null,
      uploaded_at: new Date().toISOString(),
      state: "uploaded",
      error: null,
      active: true,
    };
    record.documents.push(document);
    record.revision += 1;
    return { duplicate: false, document: structuredClone(document), revision: record.revision };
  }

  async deleteDocument(caseId: string, documentId: string, expectedRevision: number): Promise<{ revision: number }> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    const doc = record.documents.find((d) => d.document_id === documentId);
    if (!doc) throw notFound();
    doc.active = false;
    record.revision += 1;
    return { revision: record.revision };
  }

  getDocumentContentUrl(documentId: string): string {
    return `data:text/plain,${encodeURIComponent(`Fixture — no real file content for ${documentId}`)}`;
  }

  async getDocumentPage(documentId: string, page: number): Promise<DocumentPage> {
    return {
      document_id: documentId,
      page,
      image_url: null,
      source_text: "Aperçu non disponible en mode démonstration.",
      method: null,
      quality: null,
    };
  }

  async startAnalysis(
    caseId: string,
    expectedRevision: number,
    _idempotencyKey: string,
  ): Promise<{ job_id: string; case_id: string; revision: number }> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    if (record.intake.status !== "ready") throw intakeNotReady(record.intake);

    const existing = record.analyses.at(-1);
    let analysis: Analysis;
    if (existing) {
      analysis = existing;
    } else {
      analysis = {
        analysis_id: this.store.nextId("RUN"),
        case_id: record.case_id,
        revision: record.revision,
        status: "ready",
        execution_mode: "fixture",
        checklist_version: "tn-goods-v1",
        legal_coverage: FIXTURE_CONFIG.legal_coverage[record.claim.case_type] ?? "unvalidated",
        coverage: { reviewed_pages: 0, unreadable_pages: 0, rejected_facts: 0 },
        checks: [],
        reconciliation: null,
      };
      record.analyses.push(analysis);
    }

    const job: Job = {
      id: this.store.nextId("JOB"),
      status: "succeeded",
      phase: "publishing",
      error: null,
      result_analysis_id: analysis.analysis_id,
      result_export_id: null,
    };
    record.jobs.push(job);
    return { job_id: job.id, case_id: record.case_id, revision: record.revision };
  }

  async getJob(jobId: string): Promise<Job> {
    this.requireAuth();
    for (const record of this.store.cases.values()) {
      const job = record.jobs.find((j) => j.id === jobId);
      if (job) return structuredClone(job);
    }
    throw notFound();
  }

  async getAnalysis(analysisId: string): Promise<Analysis> {
    this.requireAuth();
    for (const record of this.store.cases.values()) {
      const analysis = record.analyses.find((a) => a.analysis_id === analysisId);
      if (analysis) return structuredClone(analysis);
    }
    throw notFound();
  }

  async respondToFinding(
    findingId: string,
    expectedRevision: number,
    action: FindingAction,
    explanation: string | null,
    documentIds: string[],
  ): Promise<{ revision: number; response: FindingResponse }> {
    const user = this.requireAuth();
    for (const record of this.store.cases.values()) {
      if (record.owner_id !== user.id) continue;
      const hasFinding = record.analyses.some((a) => a.checks.some((c) => c.finding_id === findingId));
      if (!hasFinding) continue;
      this.requireRevision(record, expectedRevision);
      const response: FindingResponse = {
        finding_id: findingId,
        action,
        explanation,
        document_ids: documentIds,
        created_at: new Date().toISOString(),
      };
      record.responses[findingId] = response;
      record.revision += 1;
      return { revision: record.revision, response: structuredClone(response) };
    }
    throw notFound();
  }

  async listRecipients(): Promise<ListResponse<Recipient>> {
    this.requireAuth();
    return { items: structuredClone(FIXTURE_RECIPIENTS), next_cursor: null };
  }

  async createExport(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    _acknowledgeUnresolved: boolean,
    _idempotencyKey: string,
  ): Promise<{ job_id: string; export_id: string }> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    const analysis = record.analyses.find((a) => a.analysis_id === analysisId);
    if (!analysis) throw notFound();

    const export_id = this.store.nextId("EXPORT");
    const job: Job = {
      id: this.store.nextId("JOB"),
      status: "succeeded",
      phase: "packaging",
      error: null,
      result_analysis_id: analysis.analysis_id,
      result_export_id: export_id,
    };
    record.jobs.push(job);
    return { job_id: job.id, export_id };
  }

  getExportContentUrl(exportId: string): string {
    return `data:text/plain,${encodeURIComponent(`Fixture — no real export package for ${exportId}`)}`;
  }

  async createSubmission(
    caseId: string,
    expectedRevision: number,
    analysisId: string,
    recipientId: string,
    _acknowledgeUnresolved: boolean,
    _idempotencyKey: string,
  ): Promise<Submission> {
    const record = this.requireCase(caseId);
    this.requireRevision(record, expectedRevision);
    const analysis = record.analyses.find((a) => a.analysis_id === analysisId);
    if (!analysis) throw notFound();
    const recipient = FIXTURE_RECIPIENTS.find((r) => r.recipient_id === recipientId);
    if (!recipient) throw notFound();

    const submission_id = this.store.nextId("SUB");
    const submitted_at = new Date().toISOString();
    const stored = {
      submission_id,
      case_id: record.case_id,
      revision: record.revision,
      analysis_id: analysis.analysis_id,
      recipient_id: recipientId,
      status: "submitted",
      submitted_at,
      snapshot: {
        claim: structuredClone(record.claim),
        documents: structuredClone(record.documents),
        analysis: structuredClone(analysis),
        responses: Object.values(record.responses).map((r) => structuredClone(r)),
      },
      events: [],
    };
    this.store.submissions.set(submission_id, stored);
    record.submissions.push({
      submission_id,
      revision: record.revision,
      recipient_id: recipientId,
      status: stored.status,
      submitted_at,
    });
    return {
      submission_id,
      case_id: record.case_id,
      revision: record.revision,
      analysis_id: analysis.analysis_id,
      recipient_id: recipientId,
      status: stored.status,
      submitted_at,
    };
  }

  async listReviewerSubmissions(): Promise<ListResponse<ReviewerSubmissionSummary>> {
    const user = this.requireAuth();
    if (user.role !== "reviewer") throw notFound();
    const items: ReviewerSubmissionSummary[] = [...this.store.submissions.values()].map((s) => ({
      submission_id: s.submission_id,
      case_id: s.case_id,
      claimant_name: s.snapshot.claim.claimant_name,
      status: s.status,
      submitted_at: s.submitted_at,
    }));
    return { items, next_cursor: null };
  }

  async getReviewerSubmission(submissionId: string): Promise<ReviewerSubmissionDetail> {
    const user = this.requireAuth();
    if (user.role !== "reviewer") throw notFound();
    const stored = this.store.submissions.get(submissionId);
    if (!stored) throw notFound();
    return {
      submission_id: stored.submission_id,
      case_id: stored.case_id,
      revision: stored.revision,
      claim: structuredClone(stored.snapshot.claim),
      documents: structuredClone(stored.snapshot.documents),
      analysis: structuredClone(stored.snapshot.analysis),
      responses: structuredClone(stored.snapshot.responses),
      events: structuredClone(stored.events),
    };
  }

  async createReviewEvent(
    submissionId: string,
    eventType: ReviewEventType,
    message: string | null,
  ): Promise<ReviewEvent> {
    const user = this.requireAuth();
    if (user.role !== "reviewer") throw notFound();
    const stored = this.store.submissions.get(submissionId);
    if (!stored) throw notFound();

    const event: ReviewEvent = {
      event_id: this.store.nextId("EVT"),
      event_type: eventType,
      message,
      created_at: new Date().toISOString(),
    };
    stored.events.push(event);
    stored.status = eventType;

    const caseRecord = this.store.cases.get(stored.case_id);
    if (caseRecord) {
      caseRecord.activity.push({
        id: this.store.nextId("activity"),
        type: `reviewer_${eventType}`,
        message: message ?? `Le relecteur a effectué l'action : ${eventType}.`,
        created_at: event.created_at,
      });
    }

    return structuredClone(event);
  }
}
