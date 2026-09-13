import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { ReviewerSubmissionSummary } from "../api/types";
import { Badge } from "../components/Badge";
import { READINESS_LABEL, READINESS_TONE } from "../lib/findingLabels";
import { reviewerStatusLabel, reviewerStatusTone } from "../lib/reviewerLabels";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; submissions: ReviewerSubmissionSummary[] };

function formatDateFr(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR");
}

/** Reviewer inbox (frontend.md "Reviewer back office"): only submissions assigned to the signed-in reviewer. */
export function ReviewerSubmissionsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    caseApi
      .listReviewerSubmissions()
      .then(({ items }) => {
        if (!cancelled) setState({ status: "loaded", submissions: items });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Impossible de charger les dossiers assignés.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-xl font-semibold text-text">Dossiers assignés</h1>

      {state.status === "loading" && (
        <ul className="mt-6 flex flex-col gap-3" aria-label="Chargement des dossiers assignés">
          {[0, 1, 2].map((i) => (
            <li key={i} className="skeleton h-20 rounded-md border border-border" />
          ))}
        </ul>
      )}

      {state.status === "error" && (
        <p role="alert" className="mt-6 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      )}

      {state.status === "loaded" && state.submissions.length === 0 && (
        <div className="mt-6 rounded-md border border-border bg-surface p-8 text-center">
          <p className="text-sm text-text-muted">Aucun dossier ne vous a été assigné pour l'instant.</p>
        </div>
      )}

      {state.status === "loaded" && state.submissions.length > 0 && (
        <ul className="mt-6 flex flex-col gap-3">
          {state.submissions.map((s) => (
            <li key={s.submission_id}>
              <Link
                to={`/reviewer/submissions/${s.submission_id}`}
                className="block rounded-md border border-border bg-surface p-4 no-underline shadow-raised transition-[border-color,box-shadow] hover:border-border-strong hover:shadow-lifted"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-md font-medium text-text" dir="auto">
                      {s.claimant_name}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      Dossier <span className="tabular">{s.case_id}</span>
                      {s.revision !== undefined && (
                        <>
                          {" "}
                          · révision <span className="tabular">{s.revision}</span>
                        </>
                      )}
                      {" · "}
                      soumis le <span className="tabular">{formatDateFr(s.submitted_at)}</span>
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Badge tone={reviewerStatusTone(s.status)}>{reviewerStatusLabel(s.status)}</Badge>
                    <Badge tone={READINESS_TONE[s.readiness.status]}>{READINESS_LABEL[s.readiness.status]}</Badge>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
