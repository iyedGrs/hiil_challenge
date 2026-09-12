import type { BadgeTone } from "../components/Badge";
import type { IntakeStatus } from "../api/types";

/** Shared label/tone mapping so the cases list and case detail header agree (DESIGN.md semantic colors). */
export const INTAKE_STATUS_LABEL: Record<IntakeStatus, string> = {
  not_checked: "Non vérifié",
  ready: "Prêt",
  needs_information: "Informations requises",
  gate_unavailable: "Vérification indisponible",
};

export const INTAKE_STATUS_TONE: Record<IntakeStatus, BadgeTone> = {
  not_checked: "info",
  ready: "success",
  needs_information: "warning",
  gate_unavailable: "danger",
};
