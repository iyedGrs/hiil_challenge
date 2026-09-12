import type { CaseApi } from "./CaseApi";
import { FixtureCaseApi } from "./fixture/FixtureCaseApi";
import { HttpCaseApi } from "./http/HttpCaseApi";

export type DataMode = "fixture" | "http";

/** Pure so adapter-selection failure can be unit tested without touching import.meta.env. */
export function resolveDataMode(raw: string | undefined): DataMode {
  const value = raw ?? "fixture";
  if (value === "fixture" || value === "http") return value;
  // FE-12 / L3: an unknown value must fail loudly, never silently fall back.
  throw new Error(`Unknown VITE_DATA_MODE "${value}" — expected "fixture" or "http".`);
}

export const dataMode: DataMode = resolveDataMode(import.meta.env.VITE_DATA_MODE);

export function createCaseApi(mode: DataMode = dataMode): CaseApi {
  return mode === "fixture" ? new FixtureCaseApi() : new HttpCaseApi();
}

/** The app's single CaseApi instance, picked once at startup. */
export const caseApi: CaseApi = createCaseApi();

export type { CaseApi } from "./CaseApi";
export { ApiError } from "./ApiError";
export * from "./types";
