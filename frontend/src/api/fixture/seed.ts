import type { AppConfig, AuthUser, CheckFinding, Claim, DocumentPage, DocumentRecord, Recipient } from "../types";

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

// PROVISIONAL (B9 gap): B9 does not enumerate how a recipient maps to a
// signed-in reviewer account; assumed a fixed recipient->reviewer assignment
// so the inbox (UI-08) only ever lists submissions assigned to the signed-in
// reviewer (frontend.md "Reviewer back office").
export const RECIPIENT_REVIEWER_ASSIGNMENTS: Record<string, string> = {
  recipient_reviewer_demo: "user_reviewer",
};

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

/**
 * Demo case documents, covering every DocumentState the workspace must
 * distinguish (frontend.md F4/FE-03) plus one Arabic-text page (FE-10).
 */
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
    size_bytes: 182_340,
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
    size_bytes: 421_980,
  },
  {
    document_id: "DOC_003",
    filename: "recu_partiel.jpg",
    document_type: "receipt",
    pages: 1,
    uploaded_at: "2026-06-11T09:04:00Z",
    state: "partial",
    error: "Une partie du texte n'a pas pu être extraite ; la qualité de l'image est faible.",
    active: true,
    size_bytes: 612_500,
  },
  {
    document_id: "DOC_004",
    filename: "correspondance_chiffree.pdf",
    document_type: null,
    pages: 1,
    uploaded_at: "2026-06-11T09:06:00Z",
    state: "unreadable",
    error: "Ce fichier est illisible ou protégé ; il n'a pas pu être analysé.",
    active: true,
    size_bytes: 97_200,
  },
  {
    document_id: "DOC_005",
    filename: "lettre_reclamation_ar.pdf",
    document_type: "correspondence",
    pages: 1,
    uploaded_at: "2026-06-11T09:08:00Z",
    state: "ready",
    error: null,
    active: true,
    size_bytes: 154_760,
  },
];

/** Seeded page previews for `getDocumentPage` (B9 gap: shape assumed, see progress.md). */
export const DEMO_DOCUMENT_PAGES: Record<string, DocumentPage[]> = {
  DOC_001: [
    {
      document_id: "DOC_001",
      page: 1,
      image_url: null,
      source_text:
        "Facture n° 0001 — Mobilier de bureau livré le 10/06/2026. Montant total : 20 000,000 TND. Échéance de paiement : 10/07/2026.",
      method: "embedded_text",
      quality: "bonne",
    },
  ],
  DOC_002: [
    {
      document_id: "DOC_002",
      page: 1,
      image_url: null,
      source_text: "Contrat de fourniture signé le 01/06/2026 entre Amina Gharbi et Client Démo SARL.",
      method: "embedded_text",
      quality: "bonne",
    },
    {
      document_id: "DOC_002",
      page: 2,
      image_url: null,
      source_text: "Conditions de livraison et modalités de paiement — annexe signée par les deux parties.",
      method: "embedded_text",
      quality: "bonne",
    },
  ],
  DOC_003: [
    {
      document_id: "DOC_003",
      page: 1,
      image_url: null,
      source_text: "Reçu partiel — [zone illisible] ... solde restant [zone illisible].",
      method: "ocr",
      quality: "faible",
    },
  ],
  DOC_004: [
    {
      document_id: "DOC_004",
      page: 1,
      image_url: null,
      source_text: null,
      method: null,
      quality: "illisible",
    },
  ],
  DOC_005: [
    {
      document_id: "DOC_005",
      page: 1,
      image_url: null,
      source_text: "نطالب بتسوية باقي المستحقات المتعلقة بالفاتورة رقم 0001 في أقرب الآجال.",
      method: "ocr",
      quality: "bonne",
    },
  ],
};

/**
 * The exact published check from frontend.md F5, plus its plain subject
 * label (PROVISIONAL B9 gap, see types.ts CheckFinding.subject_label).
 */
export const DEMO_CASE_CHECK: CheckFinding = {
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
  evidence_refs: [],
  reviewed_document_ids: ["DOC_001", "DOC_002"],
  legal_reference_ids: [],
  actions: ["add_evidence", "explain_unavailable", "disagree"],
};

/** Satisfied finding citing both a French page (DOC_001) and the seeded Arabic page (DOC_005). */
export const DEMO_CASE_CHECK_SATISFIED: CheckFinding = {
  check_id: "invoice_issuance",
  subject_id: "invoice_0001",
  subject_label: "Émission de la facture — facture n° 0001",
  finding_id: "finding_invoice_issuance_0001",
  result: "satisfied",
  reason_code: "EVIDENCE_FOUND",
  finding_status: "resolved",
  delta: "resolved",
  basis: "checklist",
  message: "La facture correspond à la réclamation et est corroborée par la correspondance versée au dossier.",
  evidence_refs: [
    { fact_id: "fact_invoice_amount", document_id: "DOC_001", page: 1, source_text: "Facture n° 0001 — Mobilier de bureau livré le 10/06/2026. Montant total : 20 000,000 TND." },
    { fact_id: "fact_claim_correspondence", document_id: "DOC_005", page: 1, source_text: "نطالب بتسوية باقي المستحقات المتعلقة بالفاتورة رقم 0001 في أقرب الآجال." },
  ],
  reviewed_document_ids: ["DOC_001", "DOC_005"],
  legal_reference_ids: [],
  actions: ["disagree"],
};

/** Unassessable finding pointing at the seeded unreadable document. */
export const DEMO_CASE_CHECK_UNREADABLE: CheckFinding = {
  check_id: "correspondence_readability",
  subject_id: "correspondance_chiffree",
  subject_label: "Lisibilité — correspondance jointe",
  finding_id: "finding_correspondence_readability_0001",
  result: "unassessable",
  reason_code: "SOURCE_UNREADABLE",
  finding_status: "open",
  delta: "new",
  basis: "deterministic",
  message: "Ce document n'a pas pu être analysé : le fichier est illisible ou protégé.",
  evidence_refs: [],
  reviewed_document_ids: [],
  legal_reference_ids: [],
  actions: ["add_evidence", "explain_unavailable", "disagree"],
};

/** Code-owned not_applicable finding (B9: "the last is set by code"). */
export const DEMO_CASE_CHECK_NOT_APPLICABLE: CheckFinding = {
  check_id: "payment_plan_terms",
  subject_id: "requested_outcome",
  subject_label: "Modalités d'échelonnement",
  finding_id: "finding_payment_plan_terms_0001",
  result: "not_applicable",
  reason_code: "NOT_APPLICABLE",
  finding_status: null,
  delta: "not_applicable",
  basis: "claim",
  message: "Ce contrôle ne s'applique pas : le paiement échelonné n'a pas été demandé pour ce dossier.",
  evidence_refs: [],
  reviewed_document_ids: [],
  legal_reference_ids: [],
  actions: [],
};

/** Contradicted amount-reconciliation finding (F5 "code-generated amount discrepancy"). */
export const DEMO_CASE_CHECK_AMOUNT_DISCREPANCY: CheckFinding = {
  check_id: "claimed_amount_reconciliation",
  subject_id: "invoice_0001",
  subject_label: "Cohérence du montant réclamé",
  finding_id: "finding_amount_reconciliation_0001",
  result: "contradicted",
  reason_code: "CONFLICT",
  finding_status: "open",
  delta: "new",
  basis: "deterministic",
  message: "Le montant réclamé diffère du solde documenté par les pièces fournies.",
  evidence_refs: [
    { fact_id: "fact_receipt_partial", document_id: "DOC_003", page: 1, source_text: "Reçu partiel — [zone illisible] ... solde restant [zone illisible]." },
  ],
  reviewed_document_ids: ["DOC_001", "DOC_002", "DOC_003"],
  legal_reference_ids: [],
  actions: ["correct_claim", "disagree"],
};

/** Fresh clones of every baseline finding seeded for a case's very first published analysis. */
export function buildBaselineChecks(): CheckFinding[] {
  return [
    structuredClone(DEMO_CASE_CHECK),
    structuredClone(DEMO_CASE_CHECK_SATISFIED),
    structuredClone(DEMO_CASE_CHECK_UNREADABLE),
    structuredClone(DEMO_CASE_CHECK_NOT_APPLICABLE),
    structuredClone(DEMO_CASE_CHECK_AMOUNT_DISCREPANCY),
  ];
}

/**
 * UI-06: a check that only appears once a case is reassessed for the second
 * time, so the P6 demo can show the `new` delta appearing on a later run
 * rather than only on the very first published analysis.
 */
export const DEMO_CASE_CHECK_PAYMENT_DUE: CheckFinding = {
  check_id: "payment_due_status",
  subject_id: "invoice_0001",
  subject_label: "Échéance de paiement — facture n° 0001",
  finding_id: "finding_payment_due_status_0001",
  result: "unassessable",
  reason_code: "PARTIAL_COVERAGE",
  finding_status: "open",
  delta: "new",
  basis: "checklist",
  message: "L'échéance de paiement n'a pas pu être confirmée avec les pièces examinées jusqu'ici.",
  evidence_refs: [],
  reviewed_document_ids: [],
  legal_reference_ids: [],
  actions: ["add_evidence", "explain_unavailable", "disagree"],
};

/** P6: backend calculates a 15,000 TND documented balance against the 20,000 TND claim. */
export const DEMO_CASE_RECONCILIATION = {
  documented_balance: "15000.000",
  currency: "TND",
  source_fact_ids: ["fact_invoice_amount", "fact_receipt_partial"],
  coverage_note:
    "Solde calculé à partir des pièces lisibles ; le reçu partiel n'a pas pu être totalement vérifié.",
};
