import type { BadgeTone } from "../components/Badge";
import type { ReviewEventType } from "../api/types";

/**
 * PROVISIONAL (B9 gap): submission/review status strings are not enumerated
 * as a closed set by B9; modeled from the lifecycle implied by frontend.md
 * ("submitted" then reviewer actions received/clarification_requested/reviewed).
 */
export const REVIEWER_STATUS_LABEL: Record<string, string> = {
  submitted: "Soumis",
  received: "Reçu",
  clarification_requested: "Clarification demandée",
  reviewed: "Examiné",
};

export const REVIEWER_STATUS_TONE: Record<string, BadgeTone> = {
  submitted: "info",
  received: "muted",
  clarification_requested: "warning",
  reviewed: "success",
};

export const REVIEW_EVENT_TYPE_LABEL: Record<ReviewEventType, string> = {
  received: "Reçu",
  clarification_requested: "Clarification demandée",
  reviewed: "Examiné",
};

export function reviewerStatusLabel(status: string): string {
  return REVIEWER_STATUS_LABEL[status] ?? status;
}

export function reviewerStatusTone(status: string): BadgeTone {
  return REVIEWER_STATUS_TONE[status] ?? "muted";
}
