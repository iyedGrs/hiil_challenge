import { useEffect, useId, useRef, useState } from "react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CaseDetail, ExportStatus, Recipient, Submission } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { JobProgress } from "./JobProgress";
import { useJobPolling } from "../lib/useJobPolling";
import { ANALYSIS_STATUS_LABEL, ANALYSIS_STATUS_TONE, LEGAL_COVERAGE_LABEL, LEGAL_COVERAGE_TONE } from "../lib/findingLabels";

interface SubmissionPanelProps {
  caseId: string;
  detail: CaseDetail;
  onReload: () => void;
  onNavigateToChecks: () => void;
}

function formatDateFr(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR");
}

/**
 * "Soumission" tab: final review, export and submission (frontend.md
 * "Final review and submission", FE-08). Only ever calls export/submission
 * when a current, non-failed, published analysis backs the dossier.
 */
export function SubmissionPanel({ caseId, detail, onReload, onNavigateToChecks }: SubmissionPanelProps) {
  const analysis = detail.latest_analysis;
  const job = detail.latest_job;

  const jobFailed = job?.status === "failed";
  const isOutdated = analysis !== null && (analysis.status === "outdated" || analysis.revision < detail.revision);
  const isPartial = analysis !== null && analysis.status === "partial" && !isOutdated;
  const unresolvedFindings = analysis ? analysis.checks.filter((c) => c.finding_status === "open") : [];
  const responseByFindingId = new Map(detail.responses.map((r) => [r.finding_id, r]));

  const blocked = !analysis || jobFailed || isOutdated;
  const blockedReason = !analysis
    ? "Aucune analyse publiée n'est disponible pour ce dossier."
    : jobFailed
      ? "La dernière tentative d'analyse a échoué. Une analyse publiée est requise avant l'export ou la soumission."
      : isOutdated
        ? `Cette analyse porte sur une révision antérieure du dossier (analyse ${analysis!.revision} / dossier ${detail.revision}).`
        : null;

  const [ackPartial, setAckPartial] = useState(false);
  const [ackUnresolved, setAckUnresolved] = useState(false);
  const acknowledgeUnresolved = ackPartial || ackUnresolved;
  const readyToProceed = !blocked && (!isPartial || ackPartial) && (unresolvedFindings.length === 0 || ackUnresolved);

  // ---- Export -------------------------------------------------------------
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<ExportStatus | "idle">("idle");
  const [exportResultId, setExportResultId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportIdempotencyKeyRef = useRef<string | null>(null);

  const exportPolling = useJobPolling({
    jobId: exportJobId,
    onSucceeded: (finishedJob) => {
      setExportJobId(null);
      setExportStatus("ready");
      setExportResultId(finishedJob.result_export_id);
    },
    onFailed: () => {
      setExportJobId(null);
      setExportStatus("failed");
    },
    onSuperseded: () => {
      setExportJobId(null);
      onReload();
    },
  });

  async function handleExport(): Promise<void> {
    if (!analysis) return;
    setExportError(null);
    setExporting(true);
    const idempotencyKey = exportIdempotencyKeyRef.current ?? crypto.randomUUID();
    exportIdempotencyKeyRef.current = idempotencyKey;
    try {
      const result = await caseApi.createExport(caseId, detail.revision, analysis.analysis_id, acknowledgeUnresolved, idempotencyKey);
      exportIdempotencyKeyRef.current = null;
      setExportStatus("generating");
      setExportJobId(result.job_id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        exportIdempotencyKeyRef.current = null;
        onReload();
      } else {
        setExportError(err instanceof ApiError ? err.message : "Impossible de générer le dossier. Réessayez.");
      }
    } finally {
      setExporting(false);
    }
  }

  // ---- Recipients / submission ---------------------------------------------
  const recipientFieldId = useId();
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [recipientId, setRecipientId] = useState<string>("");
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submissionResult, setSubmissionResult] = useState<Submission | null>(null);
  const submissionIdempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    caseApi
      .listRecipients()
      .then((res) => setRecipients(res.items))
      .catch(() => setRecipients([]));
  }, []);

  const selectedRecipient = recipients.find((r) => r.recipient_id === recipientId) ?? null;

  async function handleSubmit(): Promise<void> {
    if (!analysis || !recipientId) return;
    setSubmitError(null);
    setSubmitting(true);
    const idempotencyKey = submissionIdempotencyKeyRef.current ?? crypto.randomUUID();
    submissionIdempotencyKeyRef.current = idempotencyKey;
    try {
      const result = await caseApi.createSubmission(
        caseId,
        detail.revision,
        analysis.analysis_id,
        recipientId,
        acknowledgeUnresolved,
        idempotencyKey,
      );
      submissionIdempotencyKeyRef.current = null;
      setSubmissionResult(result);
      setConfirmed(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "REVISION_CONFLICT") {
        submissionIdempotencyKeyRef.current = null;
        setSubmitError("Le dossier a changé, vérifiez-le à nouveau");
        setConfirmed(false);
        onReload();
      } else {
        setSubmitError(err instanceof ApiError ? err.message : "Impossible de transmettre le dossier. Réessayez.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const activeDocuments = detail.documents.filter((d) => d.active);

  return (
    <div className="flex flex-col gap-6">
      {/* 1. Review summary */}
      <div className="rounded-md border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-md font-medium text-text">Récapitulatif avant transmission</h2>
          <span className="tabular text-xs text-text-subtle">Révision {detail.revision}</span>
        </div>
        <p className="mt-1 text-xs text-text-muted">
          Cet état reflète l'avancement du dossier dans le flux de préparation ; il ne constitue pas une certification
          juridique.
        </p>

        {analysis && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone={ANALYSIS_STATUS_TONE[analysis.status]}>{ANALYSIS_STATUS_LABEL[analysis.status]}</Badge>
            <Badge tone={LEGAL_COVERAGE_TONE[analysis.legal_coverage]}>{LEGAL_COVERAGE_LABEL[analysis.legal_coverage]}</Badge>
          </div>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm text-text-muted sm:grid-cols-3">
          <div>
            <dt className="text-xs text-text-subtle">Réclamant</dt>
            <dd className="text-text">{detail.claim.claimant_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Partie adverse</dt>
            <dd className="text-text">{detail.claim.counterparty_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-subtle">Montant réclamé</dt>
            <dd className="tabular text-text">
              {detail.claim.claimed_amount} {detail.claim.currency}
            </dd>
          </div>
        </dl>

        <div className="mt-4">
          <h3 className="text-xs font-medium text-text-subtle">Index des pièces (documents actifs)</h3>
          {activeDocuments.length === 0 ? (
            <p className="mt-1 text-sm text-text-muted">Aucun document actif.</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-1 text-sm text-text-muted">
              {activeDocuments.map((doc) => (
                <li key={doc.document_id}>{doc.filename}</li>
              ))}
            </ul>
          )}
        </div>

        {analysis && (
          <div className="mt-4">
            <h3 className="text-xs font-medium text-text-subtle">
              Constats non résolus (<span className="tabular">{unresolvedFindings.length}</span>)
            </h3>
            {unresolvedFindings.length === 0 ? (
              <p className="mt-1 text-sm text-text-muted">Aucun constat ouvert.</p>
            ) : (
              <ul className="mt-1 flex flex-col gap-2">
                {unresolvedFindings.map((finding) => {
                  const response = responseByFindingId.get(finding.finding_id);
                  return (
                    <li key={finding.finding_id} className="rounded-sm border border-border bg-surface-muted p-2 text-sm">
                      <p className="font-medium text-text">{finding.subject_label}</p>
                      <p className="text-text-muted">{finding.message}</p>
                      {response && (
                        <p className="mt-1 text-xs text-text-subtle">
                          Réponse du préparateur : {response.explanation ?? "(sans explication)"}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* 2. Gating */}
      {blockedReason && (
        <div role="alert" className="rounded-md border border-danger bg-danger-bg p-4 text-sm text-danger">
          <p>{blockedReason}</p>
          <Button variant="secondary" className="mt-2" onClick={onNavigateToChecks}>
            Aller à Vérifications
          </Button>
        </div>
      )}

      {!blocked && isPartial && (
        <label className="flex items-start gap-2 rounded-md border border-warning bg-warning-bg p-4 text-sm text-warning">
          <input type="checkbox" checked={ackPartial} onChange={(e) => setAckPartial(e.target.checked)} className="mt-0.5" />
          <span>
            Cette analyse est partielle ({analysis!.coverage.unreadable_pages} page(s) illisible(s),{" "}
            {analysis!.coverage.rejected_facts} élément(s) rejeté(s)). Je reconnais ces limites et souhaite poursuivre.
          </span>
        </label>
      )}

      {!blocked && unresolvedFindings.length > 0 && (
        <label className="flex items-start gap-2 rounded-md border border-warning bg-warning-bg p-4 text-sm text-warning">
          <input
            type="checkbox"
            checked={ackUnresolved}
            onChange={(e) => setAckUnresolved(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Des constats restent non résolus et seront transmis tels quels. Je reconnais qu'ils sont conservés dans le
            dossier.
          </span>
        </label>
      )}

      {/* 3. Export */}
      <div className="rounded-md border border-border bg-surface p-4">
        <h2 className="text-md font-medium text-text">Dossier à télécharger</h2>
        {exportJobId && exportPolling.job && (
          <div className="mt-3">
            <JobProgress job={exportPolling.job} stillProcessing={exportPolling.stillProcessing} transientError={exportPolling.transientError} />
          </div>
        )}
        {exportStatus === "ready" && exportResultId && (
          <p className="mt-3 text-sm text-success">
            Le dossier est prêt.{" "}
            <a
              href={caseApi.getExportContentUrl(exportResultId)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium underline"
            >
              Télécharger le dossier
            </a>
          </p>
        )}
        {exportStatus === "failed" && (
          <p role="alert" className="mt-3 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            La génération du dossier a échoué.
          </p>
        )}
        {exportError && (
          <p role="alert" className="mt-3 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            {exportError}
          </p>
        )}
        {!exportJobId && (
          <div className="mt-3">
            <Button variant="secondary" onClick={() => void handleExport()} disabled={!readyToProceed || exporting}>
              Générer le dossier
            </Button>
          </div>
        )}
      </div>

      {/* 4. Submission */}
      <div className="rounded-md border border-border bg-surface p-4">
        <h2 className="text-md font-medium text-text">Transmission pour examen</h2>

        {submissionResult ? (
          <div className="mt-3 rounded-sm bg-success-bg p-3 text-sm text-success">
            <p className="font-medium">Transmis pour examen sur la plateforme</p>
            <p className="mt-1 tabular">
              Soumission {submissionResult.submission_id} · révision {submissionResult.revision} ·{" "}
              {recipients.find((r) => r.recipient_id === submissionResult.recipient_id)?.name ?? submissionResult.recipient_id} ·{" "}
              {formatDateFr(submissionResult.submitted_at)}
            </p>
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            <div>
              <label htmlFor={recipientFieldId} className="text-xs font-medium text-text-muted">
                Destinataire
              </label>
              <select
                id={recipientFieldId}
                value={recipientId}
                onChange={(e) => {
                  setRecipientId(e.target.value);
                  setConfirmed(false);
                }}
                className="ml-2 rounded-sm border border-border-strong bg-surface px-2 py-1 text-sm text-text"
              >
                <option value="">Sélectionner…</option>
                {recipients.map((recipient) => (
                  <option key={recipient.recipient_id} value={recipient.recipient_id}>
                    {recipient.name}
                  </option>
                ))}
              </select>
            </div>

            {recipientId && (
              <label className="flex items-start gap-2 text-sm text-text">
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5" />
                <span>
                  Je confirme la transmission du dossier version (révision {detail.revision}) à{" "}
                  {selectedRecipient?.name ?? recipientId}.
                </span>
              </label>
            )}

            {submitError && (
              <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
                {submitError}
              </p>
            )}

            <div>
              <Button
                onClick={() => void handleSubmit()}
                disabled={!readyToProceed || !recipientId || !confirmed || submitting}
              >
                Transmettre
              </Button>
            </div>
          </div>
        )}

        {detail.submissions.length > 0 && (
          <div className="mt-6">
            <h3 className="text-xs font-medium text-text-subtle">Soumissions précédentes</h3>
            <ul className="mt-1 flex flex-col gap-1 text-sm text-text-muted">
              {detail.submissions.map((s) => (
                <li key={s.submission_id} className="tabular">
                  {s.submission_id} · révision {s.revision} ·{" "}
                  {recipients.find((r) => r.recipient_id === s.recipient_id)?.name ?? s.recipient_id} · {formatDateFr(s.submitted_at)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
