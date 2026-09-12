import type { AppConfig, AuthUser, CheckFinding, Claim, DocumentRecord, Recipient } from "../types";

/**
 * Fixture-only demo password for every seeded account. Never a real
 * credential — fixture mode never talks to a real auth system.
 */
export const FIXTURE_DEMO_PASSWORD = "demo1234";

export interface FixtureUserRecord extends AuthUser {
  password: string;
}

/** Seeded accounts: two preparers (business owner + lawyer) and one reviewer. */
export const FIXTURE_USERS: FixtureUserRecord[] = [
  {
    id: "user_amina",
    email: "amina.preparer@example.tn",
    role: "preparer",
    display_name: "Amina Gharbi",
    password: FIXTURE_DEMO_PASSWORD,
  },
  {
    id: "user_sami",
    email: "sami.lawyer@example.tn",
    role: "preparer",
    display_name: "Sami Ben Youssef",
    password: FIXTURE_DEMO_PASSWORD,
  },
  {
    id: "user_reviewer",
    email: "reviewer@example.tn",
    role: "reviewer",
    display_name: "Reviewer Démo",
    password: FIXTURE_DEMO_PASSWORD,
  },
];

export const FIXTURE_CONFIG: AppConfig = {
  case_types: ["unpaid_goods_invoice"],
  currencies: ["TND"],
  requested_outcomes: ["payment", "payment_plan"],
  limits: {
    max_active_files: 10,
    max_total_pages: 30,
    max_file_bytes: 10 * 1024 * 1024,
    max_case_bytes: 50 * 1024 * 1024,
  },
  legal_coverage: { unpaid_goods_invoice: "unvalidated" },
  execution_mode: "fixture",
};

export const FIXTURE_RECIPIENTS: Recipient[] = [{ recipient_id: "recipient_reviewer_demo", name: "Reviewer Démo" }];

/** Demo case per spec/progress.md P6: a 20,000 TND unpaid_goods_invoice claim. */
export const DEMO_CASE_CLAIM: Claim = {
  case_type: "unpaid_goods_invoice",
  claimant_name: "Amina Gharbi",
  counterparty_name: "Client Démo SARL",
  claimed_amount: "20000.000",
  currency: "TND",
  dates: {
    contract: "2026-06-01",
    delivery: "2026-06-10",
    invoice: "2026-06-10",
    payment_due: "2026-07-10",
  },
  requested_outcome: "payment",
  narrative:
    "Nous avons fourni du mobilier de bureau à ce client et la facture correspondante reste impayée à ce jour.",
  follow_up_answers: [],
};

export const DEMO_CASE_DOCUMENTS: DocumentRecord[] = [
  {
    document_id: "DOC_001",
    filename: "facture_0001.pdf",
    document_type: "invoice",
    pages: 1,
    uploaded_at: "2026-06-11T09:00:00Z",
    state: "ready",
    error: null,
    active: true,
  },
  {
    document_id: "DOC_002",
    filename: "contrat_signe.pdf",
    document_type: "contract",
    pages: 2,
    uploaded_at: "2026-06-11T09:02:00Z",
    state: "ready",
    error: null,
    active: true,
  },
];

/** The exact published check from frontend.md F5. */
export const DEMO_CASE_CHECK: CheckFinding = {
  check_id: "delivery_evidence",
  subject_id: "invoice_0001",
  finding_id: "finding_delivery_invoice_0001",
  result: "unassessable",
  reason_code: "EVIDENCE_NOT_FOUND",
  finding_status: "open",
  delta: "new",
  basis: "checklist",
  message: "Aucune preuve de réception trouvée dans les pièces examinées.",
  evidence_refs: [],
  reviewed_document_ids: ["DOC_001", "DOC_002"],
  legal_reference_ids: [],
  actions: ["add_evidence", "explain_unavailable", "disagree"],
};
