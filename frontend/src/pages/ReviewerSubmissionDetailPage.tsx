import { useEffect, useId, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { FindingResponse, ReviewerSubmissionDetail, ReviewEventType } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { DocumentPreview } from "../components/DocumentPreview";
import { FindingCard } from "../components/FindingCard";
import {
  ANALYSIS_STATUS_LABEL,
  ANALYSIS_STATUS_TONE,
  LEGAL_COVERAGE_LABEL,
  LEGAL_COVERAGE_TONE,
} from "../lib/findingLabels";
import { REVIEW_EVENT_TYPE_LABEL, reviewerStatusLabel, reviewerStatusTone } from "../lib/reviewerLabels";

type LoadState =
  | { status: "loading" }
  | { status: "denied"; message: string }
  | { status: "loaded"; detail: ReviewerSubmissionDetail };

function formatDateFr(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR");
}

/**
 * Reviewer submission detail (frontend.md "Reviewer back office", B10): the
 * immutable snapshot frozen at submission time, never the case's current
 * working revision (FE-09). Read-only everywhere except the review actions.
 */
export function ReviewerSubmissionDetailPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState<string | null>(null);
  const [posting, setPosting] = useState<ReviewEventType | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const messageFieldId = useId();

  useEffect(() => {
    if (!submissionId) return;
    caseApi
      .getReviewerSubmission(submissionId)
      .then((detail) => {
        setState({ status: "loaded", detail });
        setSelectedDocumentId(detail.documents.find((d) => d.active)?.document_id ?? null);
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError && err.status === 404
            ? "Ce dossier est introuvable ou n'est pas autorisé pour votre compte."
            : "Impossible de charger ce dossier.";
        setState({ status: "denied", message });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when navigating to a different submission
  }, [submissionId]);

  const responseByFindingId = useMemo((): Map<string, FindingResponse> => {
    if (state.status !== "loaded") return new Map();
    return new Map(state.detail.responses.map((r) => [r.finding_id, r]));
  }, [state]);

  async function handleAction(eventType: ReviewEventType): Promise<void> {
    if (state.status !== "loaded" || !submissionId) return;
    if (eventType === "clarification_requested" && message.trim().length === 0) {
      setMessageError("Un message est requis pour demander une clarification.");
      return;
    }
    setMessageError(null);
    setActionError(null);
    setPosting(eventType);
    try {
      const event = await caseApi.createReviewEvent(
        submissionId,
        eventType,
        eventType === "clarification_requested" ? message.trim() : null,
      );
      setState((prev) =>
        prev.status === "loaded"
          ? { status: "loaded", detail: { ...prev.detail, events: [...prev.detail.events, event] } }
          : prev,
      );
      setMessage("");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "L'action n'a pas pu être enregistrée. Réessayez.");
    } finally {
      setPosting(null);
    }
  }

  if (state.status === "loading") {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="skeleton h-8 w-64 rounded-sm" />
        <div className="skeleton mt-4 h-32 rounded-md" />
      </div>
    );
  }

  if (state.status === "denied") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {state.message}
        </p>
      </div>
    );
  }

  const { detail } = state;
  const analysis = detail.analysis;
  const openFindings = analysis.checks.filter((c) => c.finding_status === "open");
  const activeDocuments = detail.documents.filter((d) => d.active);
  const selectedDocument = activeDocuments.find((d) => d.document_id === selectedDocumentId) ?? null;
  // The submission's own event history is the source of truth for its current status here.
  const currentStatus = detail.events.at(-1)?.event_type ?? "submitted";

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text">
            {detail.claim.claimant_name} <span className="text-text-subtle">c.</span> {detail.claim.counterparty_name}
          </h1>
          <p className="mt-1 text-xs text-text-muted">
            Soumission <span className="tabular">{detail.submission_id}</span> · dossier{" "}
            <span className="tabular">{detail.case_id}</span> · révision <span className="tabular">{detail.revision}</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <p className="tabular text-md font-semibold text-text">
            {detail.claim.claimed_amount} {detail.claim.currency}
          </p>
          <Badge tone={reviewerStatusTone(currentStatus)}>{reviewerStatusLabel(currentStatus)}</Badge>
        </div>
      </div>

      <p className="mt-3 rounded-sm bg-surface-muted px-3 py-2 text-xs text-text-muted">
        Cet écran présente la version transmise au moment de la soumission ; les modifications ultérieures du dossier
        du préparateur n'y apparaissent pas. Marquer ce dossier « reçu » ou « examiné » n'emporte aucune acceptation
        juridique ni certification.
      </p>

      {/* Claim summary */}
      <div className="mt-6 rounded-md border border-border bg-surface p-4">
        <h2 className="text-md font-medium text-text">Réclamation</h2>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm text-text-muted sm:grid-cols-3">
          <div>
            <dt className="text-xs text-text-subtle">Réclamant</dt>
            <dd className="text-text" dir="auto">{detail.claim.claimant_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Partie adverse</dt>
            <dd className="text-text" dir="auto">{detail.claim.counterparty_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Montant réclamé</dt>
            <dd className="tabular text-text">
              {detail.claim.claimed_amount} {detail.claim.currency}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-text" dir="auto">
          {detail.claim.narrative}
        </p>
      </div>

      {/* Documents */}
      <div className="mt-6">
        <h2 className="text-md font-medium text-text">Documents sources</h2>
        {activeDocuments.length === 0 ? (
          <p className="mt-2 text-sm text-text-muted">Aucun document dans cette version transmise.</p>
        ) : (
          <div className="mt-2 flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {activeDocuments.map((doc) => (
                <Button
                  key={doc.document_id}
                  size="sm"
                  variant={doc.document_id === selectedDocumentId ? "primary" : "secondary"}
                  aria-pressed={doc.document_id === selectedDocumentId}
                  onClick={() => {
                    setSelectedDocumentId(doc.document_id);
                    setSelectedPage(1);
                  }}
                >
                  {doc.filename}
                </Button>
              ))}
            </div>
            {selectedDocument && (
              <DocumentPreview document={selectedDocument} page={selectedPage} onPageChange={setSelectedPage} />
            )}
          </div>
        )}
      </div>

      {/* Limitations */}
      <div className="mt-6 rounded-md border border-border bg-surface p-4">
        <h2 className="text-md font-medium text-text">Limites de l'analyse</h2>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone={ANALYSIS_STATUS_TONE[analysis.status]}>{ANALYSIS_STATUS_LABEL[analysis.status]}</Badge>
          <Badge tone={LEGAL_COVERAGE_TONE[analysis.legal_coverage]}>{LEGAL_COVERAGE_LABEL[analysis.legal_coverage]}</Badge>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm text-text-muted sm:grid-cols-3">
          <div>
            <dt className="text-xs text-text-subtle">Pages illisibles</dt>
            <dd className="tabular">{analysis.coverage.unreadable_pages}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Éléments rejetés</dt>
            <dd className="tabular">{analysis.coverage.rejected_facts}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Constats ouverts</dt>
            <dd className="tabular">{openFindings.length}</dd>
          </div>
        </dl>
      </div>

      {/* Validated checks (read-only) */}
      <div className="mt-6">
        <h2 className="text-md font-medium text-text">Constats validés</h2>
        <ul className="mt-2 flex flex-col gap-3">
          {analysis.checks.map((finding) => (
            <FindingCard
              key={finding.finding_id}
              finding={finding}
              revision={detail.revision}
              documents={detail.documents}
              existingResponse={responseByFindingId.get(finding.finding_id) ?? null}
              onOpenDocumentPage={(documentId) => {
                setSelectedDocumentId(documentId);
                setSelectedPage(1);
              }}
              readOnly
            />
          ))}
        </ul>
      </div>

      {/* Review actions */}
      <div className="mt-6 rounded-md border border-border bg-surface p-4">
        <h2 className="text-md font-medium text-text">Actions du relecteur</h2>

        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={posting !== null}
            onClick={() => void handleAction("received")}
          >
            Marquer comme reçu
          </Button>
          <Button
            disabled={posting !== null}
            onClick={() => void handleAction("reviewed")}
          >
            Marquer comme examiné
          </Button>
        </div>

        <div className="mt-4">
          <label htmlFor={messageFieldId} className="text-sm font-medium text-text">
            Demander une clarification
          </label>
          <textarea
            id={messageFieldId}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            dir="auto"
            aria-invalid={messageError ? true : undefined}
            className="mt-1 w-full rounded-sm border border-border-control bg-surface px-3 py-2 text-base text-text transition-colors hover:border-text-muted"
          />
          {messageError && (
            <p role="alert" className="mt-1 text-sm text-danger">
              {messageError}
            </p>
          )}
          <div className="mt-2">
            <Button
              variant="secondary"
              disabled={posting !== null}
              onClick={() => void handleAction("clarification_requested")}
            >
              Envoyer la demande de clarification
            </Button>
          </div>
        </div>

        {actionError && (
          <p role="alert" className="mt-3 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            {actionError}
          </p>
        )}

        {detail.events.length > 0 && (
          <div className="mt-6">
            <h3 className="text-xs font-medium text-text-subtle">Historique des actions</h3>
            <ul className="mt-1 flex flex-col gap-2">
              {[...detail.events].reverse().map((event) => (
                <li key={event.event_id} className="rounded-sm border border-border bg-surface-muted p-2 text-sm">
                  <p className="tabular text-xs text-text-subtle">{formatDateFr(event.created_at)}</p>
                  <p className="mt-0.5 text-text">
                    {REVIEW_EVENT_TYPE_LABEL[event.event_type]}
                    {event.message && (
                      <>
                        {" : "}
                        <span dir="auto">{event.message}</span>
                      </>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
