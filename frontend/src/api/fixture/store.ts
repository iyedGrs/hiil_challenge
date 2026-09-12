import type {
  Analysis,
  ActivityEvent,
  Claim,
  DocumentRecord,
  FindingResponse,
  Intake,
  Job,
  ReviewEvent,
  SubmissionSummary,
} from "../types";
import { DEMO_CASE_CHECK, DEMO_CASE_CLAIM, DEMO_CASE_DOCUMENTS } from "./seed";

export interface StoredCase {
  case_id: string;
  owner_id: string;
  claim: Claim;
  revision: number;
  intake: Intake;
  documents: DocumentRecord[];
  analyses: Analysis[];
  jobs: Job[];
  submissions: SubmissionSummary[];
  activity: ActivityEvent[];
  responses: Record<string, FindingResponse>;
}

export interface StoredSubmission {
  submission_id: string;
  case_id: string;
  revision: number;
  analysis_id: string;
  recipient_id: string;
  status: string;
  submitted_at: string;
  // Immutable snapshot captured at submission time (B10: "freezes claim
  // revision, document hashes/IDs, ... published run").
  snapshot: {
    claim: Claim;
    documents: DocumentRecord[];
    analysis: Analysis;
    responses: FindingResponse[];
  };
  events: ReviewEvent[];
}

export interface FixtureStore {
  cases: Map<string, StoredCase>;
  submissions: Map<string, StoredSubmission>;
  currentUserId: string | null;
  nextId: (prefix: string) => string;
}

/** Builds a fresh, self-contained fixture backend. Never shared across adapter instances. */
export function createFixtureStore(): FixtureStore {
  let counter = 0;
  const nextId = (prefix: string): string => `${prefix}_${String(++counter).padStart(4, "0")}`;

  const demoAnalysis: Analysis = {
    analysis_id: "RUN_001",
    case_id: "CASE_001",
    revision: 1,
    status: "ready",
    execution_mode: "fixture",
    checklist_version: "tn-goods-v1",
    legal_coverage: "unvalidated",
    coverage: { reviewed_pages: 3, unreadable_pages: 0, rejected_facts: 0 },
    checks: [DEMO_CASE_CHECK],
    reconciliation: null,
  };

  const demoJob: Job = {
    id: "JOB_001",
    status: "succeeded",
    phase: "publishing",
    error: null,
    result_analysis_id: demoAnalysis.analysis_id,
    result_export_id: null,
  };

  const demoCase: StoredCase = {
    case_id: "CASE_001",
    owner_id: "user_amina",
    claim: structuredClone(DEMO_CASE_CLAIM),
    revision: 1,
    intake: { status: "ready", questions: [] },
    documents: structuredClone(DEMO_CASE_DOCUMENTS),
    analyses: [demoAnalysis],
    jobs: [demoJob],
    submissions: [],
    activity: [
      {
        id: "activity_0001",
        type: "analysis_published",
        message: "Analyse initiale publiée.",
        created_at: "2026-06-11T09:05:00Z",
      },
    ],
    responses: {},
  };

  const cases = new Map<string, StoredCase>([[demoCase.case_id, demoCase]]);

  return {
    cases,
    submissions: new Map(),
    currentUserId: null,
    nextId,
  };
}
