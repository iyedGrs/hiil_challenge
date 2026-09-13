import { useEffect, useId, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle,
  DownloadSimple,
  FileArrowDown,
  PaperPlaneTilt,
  WarningCircle,
} from "@phosphor-icons/react";
import { caseApi } from "../api";
import { ApiError } from "../api/ApiError";
import type { CaseDetail, ExportStatus, Recipient, Submission } from "../api/types";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { EXPORT_PHASES, JobProgress } from "./JobProgress";
import { ReadinessNotice } from "./ReadinessNotice";
import { useToast } from "./Toast";
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

const SELECT_CLASSES =
  "rounded-sm border border-border-control bg-surface px-2.5 py-1.5 text-base text-text transition-colors hover:border-text-muted";

/**
 * "Transmission" step: final review, export and submission (frontend.md
 * "Final review and submission", FE-08). Only ever calls export/submission
 * when a current, non-failed, published analysis backs the dossier — and every
 * blocker links back to the step that can clear it.
 */
export function SubmissionPanel({ caseId, detail, onReload, onNavigateToChecks }: SubmissionPanelProps) {
  const { notify } = useToast();
  const analysis = detail.latest_analysis;
  const job = detail.latest_job;

  const readiness = detail.readiness;
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

  // Export remains available for an incomplete case (it is a preparation
  // package, not the handoff): it keeps its own acknowledgement checkboxes.
  const [ackPartial, setAckPartial] = useState(false);
  const [ackUnresolved, setAckUnresolved] = useState(false);
  const acknowledgeUnresolved = ackPartial || ackUnresolved;
  const readyToExport = !blocked && (!isPartial || ackPartial) && (unresolvedFindings.length === 0 || ackUnresolved);

  // Submission is gated by the automatic readiness verdict, plus the same
  // "no usable analysis" guard export uses: no reviewer acknowledgement step
  // (spec/progress.md change log).
  const readyToSubmit = !blocked && readiness.status === "complete";

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
      notify("success", "Le dossier est prêt à télécharger.");
    },
    onFailed: () => {
      setExportJobId(null);
      setExportStatus("failed");
      notify("danger", "La génération du dossier a échoué.");
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
        // No acknowledgement gate on submission: the readiness verdict
        // decides eligibility. Kept as a request field for compatibility.
        false,
        idempotencyKey,
      );
      submissionIdempotencyKeyRef.current = null;
      setSubmissionResult(result);
      setConfirmed(false);
      notify("success", "Dossier transmis pour examen.");
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
    <div className="flex flex-col gap-5">
      {/* 1. Review summary */}
      <div className="rounded-md border border-border bg-surface shadow-raised">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold text-text">Récapitulatif avant transmission</h2>
          <span className="tabular text-xs text-text-subtle">Révision {detail.revision}</span>
        </div>

        <div className="px-5 py-4">
          <p className="max-w-[65ch] text-sm text-text-muted">
            Cet état reflète l'avancement du dossier dans le flux de préparation ; il ne constitue pas une certification
            juridique.
          </p>

          {analysis && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <Badge tone={ANALYSIS_STATUS_TONE[analysis.status]}>{ANALYSIS_STATUS_LABEL[analysis.status]}</Badge>
              <Badge tone={LEGAL_COVERAGE_TONE[analysis.legal_coverage]}>{LEGAL_COVERAGE_LABEL[analysis.legal_coverage]}</Badge>
            </div>
          )}

          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <div>
              <dt className="text-xs text-text-subtle">Réclamant</dt>
              <dd className="mt-0.5 text-sm font-medium text-text" dir="auto">
                {detail.claim.claimant_name}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-text-subtle">Partie adverse</dt>
              <dd className="mt-0.5 text-sm font-medium text-text" dir="auto">
                {detail.claim.counterparty_name}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-text-subtle">Montant réclamé</dt>
              <dd className="tabular mt-0.5 text-sm font-medium text-text">
                {detail.claim.claimed_amount} {detail.claim.currency}
              </dd>
            </div>
          </dl>

          <div className="mt-5 border-t border-border pt-4">
            <h3 className="text-xs font-medium text-text-muted">
              Index des pièces <span className="tabular text-text-subtle">({activeDocuments.length})</span>
            </h3>
            {activeDocuments.length === 0 ? (
              <p className="mt-1.5 text-sm text-text-muted">Aucun document actif.</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {activeDocuments.map((doc) => (
                  <li
                    key={doc.document_id}
                    className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface-muted px-2.5 py-1 text-xs text-text"
                  >
                    <FileArrowDown size={13} aria-hidden="true" className="shrink-0 text-text-subtle" />
                    <span className="truncate" dir="auto">
                      {doc.filename}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {analysis && (
            <div className="mt-5 border-t border-border pt-4">
              <h3 className="text-xs font-medium text-text-muted">
                Constats non résolus (<span className="tabular">{unresolvedFindings.length}</span>)
              </h3>
              {unresolvedFindings.length === 0 ? (
                <p className="mt-1.5 flex items-center gap-1.5 text-sm text-success">
                  <CheckCircle size={15} weight="fill" aria-hidden="true" />
                  Aucun constat ouvert.
                </p>
              ) : (
                <ul className="mt-2 flex flex-col gap-2">
                  {unresolvedFindings.map((finding) => {
                    const response = responseByFindingId.get(finding.finding_id);
                    return (
                      <li key={finding.finding_id}>
                        <button
                          type="button"
                          onClick={onNavigateToChecks}
                          className="block w-full rounded-sm border border-border bg-surface-muted p-2.5 text-start transition-colors hover:border-warning hover:bg-warning-bg"
                        >
                          <span className="block text-sm font-medium text-text" dir="auto">
                            {finding.subject_label}
                          </span>
                          <span className="mt-0.5 block text-sm text-text-muted" dir="auto">
                            {finding.message}
                          </span>
                          {response && (
                            <span className="mt-1 block text-xs text-text-subtle" dir="auto">
                              Réponse du préparateur : {response.explanation ?? "(sans explication)"}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. Gating */}
      {blockedReason && (
        <div role="alert" className="rounded-md border border-danger bg-danger-bg p-4 text-sm text-danger">
          <p className="flex items-start gap-2 font-medium">
            <WarningCircle size={17} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
            {blockedReason}
          </p>
          <Button
            variant="secondary"
            size="sm"
            icon={<ArrowLeft size={14} />}
            className="mt-3"
            onClick={onNavigateToChecks}
          >
            Aller à Vérifications
          </Button>
        </div>
      )}

      {!blocked && isPartial && (
        <label className="flex items-start gap-2.5 rounded-md border border-warning bg-warning-bg p-4 text-sm text-warning">
          <input type="checkbox" checked={ackPartial} onChange={(e) => setAckPartial(e.target.checked)} className="mt-0.5" />
          <span>
            Cette analyse est partielle ({analysis!.coverage.unreadable_pages} page(s) illisible(s),{" "}
            {analysis!.coverage.rejected_facts} élément(s) rejeté(s)). Je reconnais ces limites et souhaite poursuivre.
          </span>
        </label>
      )}

      {!blocked && unresolvedFindings.length > 0 && (
        <label className="flex items-start gap-2.5 rounded-md border border-warning bg-warning-bg p-4 text-sm text-warning">
          <input
            type="checkbox"
            checked={ackUnresolved}
            onChange={(e) => setAckUnresolved(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Des constats restent non résolus et seront inclus dans le dossier téléchargé. Je reconnais ces limites et
            souhaite générer le dossier.
          </span>
        </label>
      )}

      {/* 3. Export */}
      <div className="rounded-md border border-border bg-surface p-5 shadow-raised">
        <h2 className="text-md font-semibold text-text">Dossier à télécharger</h2>
        <p className="mt-1 max-w-[65ch] text-sm text-text-muted">
          Une copie hors ligne de la réclamation, des pièces et des constats publiés.
        </p>

        {exportJobId && exportPolling.job && (
          <div className="mt-4">
            <JobProgress
              job={exportPolling.job}
              stillProcessing={exportPolling.stillProcessing}
              transientError={exportPolling.transientError}
              phases={EXPORT_PHASES}
              label="Génération du dossier"
            />
          </div>
        )}
        {exportStatus === "ready" && exportResultId && (
          <p className="mt-4 flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success">
            <CheckCircle size={16} weight="fill" aria-hidden="true" className="shrink-0" />
            Le dossier est prêt.
            <a
              href={caseApi.getExportContentUrl(exportResultId)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-medium underline"
            >
              <DownloadSimple size={15} aria-hidden="true" />
              Télécharger le dossier
            </a>
          </p>
        )}
        {exportStatus === "failed" && (
          <p role="alert" className="mt-4 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            La génération du dossier a échoué.
          </p>
        )}
        {exportError && (
          <p role="alert" className="mt-4 rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
            {exportError}
          </p>
        )}
        {!exportJobId && (
          <div className="mt-4">
            <Button
              variant="secondary"
              icon={<FileArrowDown size={15} />}
              onClick={() => void handleExport()}
              disabled={!readyToExport}
              pending={exporting}
            >
              Générer le dossier
            </Button>
          </div>
        )}
      </div>

      {/* 4. Submission */}
      <div className="rounded-md border border-border bg-surface p-5 shadow-raised">
        <h2 className="text-md font-semibold text-text">Transmission pour examen</h2>

        {/*
         * Why the recipient controls below may be unavailable. Rendered through
         * the same component the Vérifications step uses, so the verdict reads
         * identically wherever the preparer meets it.
         */}
        {!submissionResult && readiness.status !== "complete" && (
          <div className="mt-4">
            <ReadinessNotice readiness={readiness} />
          </div>
        )}

        {submissionResult ? (
          <div className="mt-4 rounded-md border border-success/30 bg-success-bg p-4 text-sm text-success animate-enter-up">
            <p className="flex items-center gap-2 font-semibold">
              <CheckCircle size={18} weight="fill" aria-hidden="true" />
              Transmis pour examen sur la plateforme
            </p>
            <p className="tabular mt-1.5">
              Soumission {submissionResult.submission_id} · révision {submissionResult.revision} ·{" "}
              {recipients.find((r) => r.recipient_id === submissionResult.recipient_id)?.name ?? submissionResult.recipient_id} ·{" "}
              {formatDateFr(submissionResult.submitted_at)}
            </p>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={recipientFieldId} className="text-sm font-medium text-text">
                Destinataire
              </label>
              <select
                id={recipientFieldId}
                value={recipientId}
                disabled={!readyToSubmit}
                onChange={(e) => {
                  setRecipientId(e.target.value);
                  setConfirmed(false);
                }}
                className={`${SELECT_CLASSES} max-w-sm disabled:opacity-50`}
              >
                <option value="">Sélectionner…</option>
                {recipients.map((recipient) => (
                  <option key={recipient.recipient_id} value={recipient.recipient_id}>
                    {recipient.name}
                  </option>
                ))}
              </select>
              {selectedRecipient && <p className="text-xs text-text-subtle">{selectedRecipient.remit}</p>}
            </div>

            {readyToSubmit && recipientId && (
              <label className="flex items-start gap-2.5 rounded-sm border border-border bg-surface-muted p-3 text-sm text-text">
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
                icon={<PaperPlaneTilt size={15} />}
                onClick={() => void handleSubmit()}
                disabled={!readyToSubmit || !recipientId || !confirmed}
                pending={submitting}
              >
                {submitting ? "Transmission…" : "Transmettre"}
              </Button>
            </div>
          </div>
        )}

        {detail.submissions.length > 0 && (
          <div className="mt-6 border-t border-border pt-4">
            <h3 className="text-xs font-medium text-text-muted">Soumissions précédentes</h3>
            <ul className="mt-2 flex flex-col divide-y divide-border">
              {detail.submissions.map((s) => (
                <li key={s.submission_id} className="tabular py-1.5 text-xs text-text-muted">
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
