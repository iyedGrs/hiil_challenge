import type { BadgeTone } from "../components/Badge";
import type {
  AnalysisStatus,
  CheckResult,
  ExecutionMode,
  FindingAction,
  FindingDelta,
  FindingStatus,
  LegalCoverageStatus,
} from "../api/types";

/**
 * Copy is neutral and never implies fraud, authenticity or a legal verdict
 * (frontend.md F4: "Evidence not found in the reviewed material" /
 * "The amount differs from the documented records", never fraud/concealment
 * wording).
 */
export const CHECK_RESULT_LABEL: Record<CheckResult, string> = {
  satisfied: "Satisfait",
  contradicted: "Contredit par les pièces",
  unassessable: "Non évaluable",
  not_applicable: "Non applicable",
};

export const CHECK_RESULT_TONE: Record<CheckResult, BadgeTone> = {
  satisfied: "success",
  contradicted: "danger",
  unassessable: "warning",
  not_applicable: "muted",
};

export const FINDING_STATUS_LABEL: Record<NonNullable<FindingStatus>, string> = {
  open: "Ouvert",
  resolved: "Résolu",
};

export const FINDING_STATUS_TONE: Record<NonNullable<FindingStatus>, BadgeTone> = {
  open: "warning",
  resolved: "success",
};

export const FINDING_DELTA_LABEL: Record<NonNullable<FindingDelta>, string> = {
  new: "Nouveau",
  resolved: "Résolu depuis la dernière analyse",
  still_open: "Toujours ouvert",
  reopened: "Rouvert",
  not_applicable: "Non applicable",
};

export const FINDING_DELTA_TONE: Record<NonNullable<FindingDelta>, BadgeTone> = {
  new: "info",
  resolved: "success",
  still_open: "muted",
  reopened: "warning",
  not_applicable: "muted",
};

export const FINDING_ACTION_LABEL: Record<FindingAction, string> = {
  add_evidence: "Ajouter une pièce",
  correct_claim: "Corriger la réclamation",
  explain_unavailable: "Expliquer l'indisponibilité",
  disagree: "Contester ce constat",
};

export const LEGAL_COVERAGE_LABEL: Record<LegalCoverageStatus, string> = {
  unvalidated: "Couverture juridique non validée",
  validated: "Couverture juridique validée par la checklist",
};

export const LEGAL_COVERAGE_TONE: Record<LegalCoverageStatus, BadgeTone> = {
  unvalidated: "warning",
  validated: "info",
};

export const EXECUTION_MODE_LABEL: Record<ExecutionMode, string> = {
  fixture: "Mode démonstration (données fixtures)",
  live: "Exécution réelle",
};

export const ANALYSIS_STATUS_LABEL: Record<AnalysisStatus, string> = {
  ready: "Publiée",
  partial: "Partielle",
  outdated: "Obsolète",
};

export const ANALYSIS_STATUS_TONE: Record<AnalysisStatus, BadgeTone> = {
  ready: "success",
  partial: "warning",
  outdated: "danger",
};
