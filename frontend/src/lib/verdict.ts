import type { Analysis, CheckFinding, CheckResult } from "../api/types";

export type VerdictTone = "success" | "warning" | "danger";

export interface AnalysisVerdict {
  tone: VerdictTone;
  /** Short, scannable headline — the one line a user reads before anything else. */
  headline: string;
  /** One neutral sentence of context. Never a legal conclusion (frontend.md F4). */
  detail: string;
  /** Findings that need the preparer's attention, most severe first. */
  issues: CheckFinding[];
}

/** Severity order used for both the verdict chips and the findings list. */
const RESULT_SEVERITY: Record<CheckResult, number> = {
  contradicted: 0,
  unassessable: 1,
  not_applicable: 2,
  satisfied: 3,
};

function isIssue(check: CheckFinding): boolean {
  return check.result === "contradicted" || check.result === "unassessable" || check.finding_status === "open";
}

/** Open issues first, then by result severity; stable within a group. */
export function sortChecksForReview(checks: CheckFinding[]): CheckFinding[] {
  return [...checks].sort((a, b) => {
    const openDelta = Number(isIssue(b)) - Number(isIssue(a));
    if (openDelta !== 0) return openDelta;
    return RESULT_SEVERITY[a.result] - RESULT_SEVERITY[b.result];
  });
}

function count(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * Reduces a published analysis to the single answer the preparer opened the
 * tab for: is anything missing, and if so what. Deliberately stays within the
 * app's honest vocabulary — "à compléter" / "à vérifier", never "conforme",
 * "validé juridiquement" or a completeness score.
 */
export function buildVerdict(analysis: Analysis, caseRevision: number): AnalysisVerdict {
  const issues = sortChecksForReview(analysis.checks).filter(isIssue);
  const contradicted = issues.filter((c) => c.result === "contradicted").length;
  const unassessable = issues.filter((c) => c.result === "unassessable").length;

  if (analysis.status === "outdated" || analysis.revision < caseRevision) {
    return {
      tone: "danger",
      headline: "Réévaluation nécessaire",
      detail: `Le dossier a changé depuis cette analyse (analyse ${analysis.revision}, dossier ${caseRevision}). Relancez l'analyse pour obtenir un résultat à jour.`,
      issues,
    };
  }

  if (issues.length === 0) {
    return {
      tone: "success",
      headline: "Aucun point à corriger",
      detail:
        analysis.status === "partial"
          ? "Toutes les vérifications évaluées sont satisfaites, mais la couverture est partielle : certaines pages n'ont pas pu être lues."
          : "Chaque vérification de la liste de contrôle est appuyée par une pièce du dossier.",
      issues,
    };
  }

  const parts: string[] = [];
  if (contradicted > 0) parts.push(count(contradicted, "écart avec les pièces", "écarts avec les pièces"));
  if (unassessable > 0) parts.push(count(unassessable, "élément non évaluable", "éléments non évaluables"));
  const others = issues.length - contradicted - unassessable;
  if (others > 0) parts.push(count(others, "constat encore ouvert", "constats encore ouverts"));

  return {
    tone: contradicted > 0 ? "danger" : "warning",
    headline: issues.length === 1 ? "1 point à traiter" : `${issues.length} points à traiter`,
    detail: `${parts.join(", ")}. Ouvrez chaque point ci-dessous pour voir la pièce concernée.`,
    issues,
  };
}
