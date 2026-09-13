import {
  CheckCircle,
  MinusCircle,
  Paperclip,
  PencilSimple,
  Prohibit,
  Question,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";
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
  satisfied: "Appuyé par les pièces",
  contradicted: "Écart avec les pièces",
  unassessable: "Non évaluable",
  not_applicable: "Non applicable",
};

export const CHECK_RESULT_TONE: Record<CheckResult, BadgeTone> = {
  satisfied: "success",
  contradicted: "danger",
  unassessable: "warning",
  not_applicable: "muted",
};

/** Reads as a clause after the result, e.g. "Écart avec les pièces · à traiter". */
export const FINDING_STATUS_LABEL: Record<NonNullable<FindingStatus>, string> = {
  open: "à traiter",
  resolved: "résolu",
};

export const FINDING_STATUS_TONE: Record<NonNullable<FindingStatus>, BadgeTone> = {
  open: "warning",
  resolved: "success",
};

export const FINDING_DELTA_LABEL: Record<NonNullable<FindingDelta>, string> = {
  new: "Apparu à cette analyse",
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

/**
 * One glyph per check result so a scan of the findings list separates outcomes
 * before any text is read. Icons come from Phosphor (no hand-rolled SVG) and
 * are always paired with the text label, never used alone as the only signal.
 */
export const CHECK_RESULT_ICON: Record<CheckResult, Icon> = {
  satisfied: CheckCircle,
  contradicted: XCircle,
  unassessable: Question,
  not_applicable: MinusCircle,
};

export const FINDING_ACTION_ICON: Record<FindingAction, Icon> = {
  add_evidence: Paperclip,
  correct_claim: PencilSimple,
  explain_unavailable: Question,
  disagree: Prohibit,
};
