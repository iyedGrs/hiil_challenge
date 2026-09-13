import type { BadgeTone } from "../components/Badge";
import type { DocumentState } from "../api/types";

/**
 * Copy must never imply authenticity (frontend.md F4: "Do not imply that
 * ready means authentic") — "Lisible", never "vérifié"/"authentique".
 */
export const DOCUMENT_STATE_LABEL: Record<DocumentState, string> = {
  uploaded: "Envoyé",
  processing: "En traitement",
  ready: "Lisible",
  partial: "Partiellement lisible",
  unreadable: "Illisible",
  rejected: "Refusé",
};

export const DOCUMENT_STATE_TONE: Record<DocumentState, BadgeTone> = {
  uploaded: "info",
  processing: "warning",
  ready: "success",
  partial: "warning",
  unreadable: "danger",
  rejected: "danger",
};

const MIB = 1024 * 1024;
const MIB_FORMAT = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

export function formatMiB(bytes: number): string {
  return `${MIB_FORMAT.format(bytes / MIB)} Mio`;
}

const DATE_FORMAT = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });

export function formatUploadedAt(iso: string): string {
  return DATE_FORMAT.format(new Date(iso));
}
