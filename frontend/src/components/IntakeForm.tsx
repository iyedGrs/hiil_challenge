import { useState, type FormEvent } from "react";
import { FloppyDisk } from "@phosphor-icons/react";
import type { AppConfig, Claim, ClaimDates, FieldError, FollowUpAnswer, IntakeQuestion } from "../api/types";
import { normalizeClaimedAmount } from "../lib/amount";
import { Button } from "./Button";
import { FormField } from "./FormField";

const DATE_FIELD_KEYS = ["contract", "delivery", "invoice", "payment_due"] as const;
type DateFieldKey = (typeof DATE_FIELD_KEYS)[number];

const DATE_LABELS: Record<DateFieldKey, string> = {
  contract: "Date du contrat",
  delivery: "Date de livraison",
  invoice: "Date de la facture",
  payment_due: "Date d'échéance de paiement",
};

const KNOWN_FIELD_KEYS = [
  "case_type",
  "claimant_name",
  "counterparty_name",
  "claimed_amount",
  "currency",
  "requested_outcome",
  "narrative",
  "dates.contract",
  "dates.delivery",
  "dates.invoice",
  "dates.payment_due",
] as const;

/** Maps a server field name (claim field or "contract"/"dates.contract" shorthand) onto our known keys, or "general". */
function normalizeFieldKey(field: string): string {
  if ((KNOWN_FIELD_KEYS as readonly string[]).includes(field)) return field;
  if ((DATE_FIELD_KEYS as readonly string[]).includes(field)) return `dates.${field}`;
  return "general";
}

interface FormValues {
  case_type: string;
  claimant_name: string;
  counterparty_name: string;
  claimed_amount: string;
  currency: string;
  dates: ClaimDates;
  requested_outcome: string;
  narrative: string;
}

function claimToValues(claim: Claim): FormValues {
  return {
    case_type: claim.case_type,
    claimant_name: claim.claimant_name,
    counterparty_name: claim.counterparty_name,
    claimed_amount: claim.claimed_amount,
    currency: claim.currency,
    dates: { ...claim.dates },
    requested_outcome: claim.requested_outcome,
    narrative: claim.narrative,
  };
}

/** One control style for every field, so hover/focus feedback is identical across the form. */
const CONTROL_CLASSES =
  "rounded-sm border border-border-control bg-surface px-3 py-2 text-base text-text transition-colors hover:border-text-muted";

export type IntakeFormResult = { ok: true } | { ok: false; fieldErrors: FieldError[]; message?: string };

interface IntakeFormProps {
  config: AppConfig;
  initialClaim: Claim;
  /** Outstanding server-issued follow-up questions (frontend.md F4 "targeted questions"). */
  questions: IntakeQuestion[];
  submitLabel: string;
  onSubmit: (claim: Claim) => Promise<IntakeFormResult>;
}

/**
 * Structured intake form shared by /cases/new (create) and the case detail
 * follow-up/edit step (frontend.md F4 "Structured intake", backend.md B3).
 * All entered values live in local state so a server or validation error
 * never discards what the user typed (FE-02).
 */
export function IntakeForm({ config, initialClaim, questions, submitLabel, onSubmit }: IntakeFormProps) {
  const [values, setValues] = useState<FormValues>(() => claimToValues(initialClaim));
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const anchoredQuestions = questions.filter((q) => normalizeFieldKey(q.field) !== "general").slice(0, 5);
  const unanchoredQuestions = questions.filter((q) => normalizeFieldKey(q.field) === "general").slice(0, 5);
  const followUpFor = (key: string): string | null =>
    anchoredQuestions.find((q) => normalizeFieldKey(q.field) === key)?.message ?? null;

  function setDate(key: DateFieldKey, raw: string): void {
    setValues((prev) => ({ ...prev, dates: { ...prev.dates, [key]: raw === "" ? null : raw } }));
  }

  function validate(amount: ReturnType<typeof normalizeClaimedAmount>): Record<string, string> {
    const next: Record<string, string> = {};
    if (values.case_type === "") next.case_type = "Sélectionnez un type de dossier.";
    if (values.claimant_name.trim().length < 1 || values.claimant_name.trim().length > 200) {
      next.claimant_name = "Le nom du demandeur doit contenir entre 1 et 200 caractères.";
    }
    if (values.counterparty_name.trim().length < 1 || values.counterparty_name.trim().length > 200) {
      next.counterparty_name = "Le nom de la partie adverse doit contenir entre 1 et 200 caractères.";
    }
    if (!amount.ok) next.claimed_amount = amount.message;
    if (values.currency === "") next.currency = "Sélectionnez une devise.";
    if (values.requested_outcome === "") next.requested_outcome = "Sélectionnez le résultat demandé.";
    const narrativeLength = values.narrative.trim().length;
    if (narrativeLength < 30 || narrativeLength > 4000) {
      next.narrative = "La description doit contenir entre 30 et 4 000 caractères.";
    }
    return next;
  }

  function buildFollowUpAnswers(): FollowUpAnswer[] {
    return unanchoredQuestions
      .map((q) => ({ question_id: q.id, answer: (answers[q.id] ?? "").trim().slice(0, 1000) }))
      .filter((a) => a.answer.length > 0);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const amount = normalizeClaimedAmount(values.claimed_amount);
    const clientErrors = validate(amount);
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      setGeneralError(null);
      return;
    }

    const claim: Claim = {
      case_type: values.case_type,
      claimant_name: values.claimant_name.trim(),
      counterparty_name: values.counterparty_name.trim(),
      claimed_amount: amount.ok ? amount.value : values.claimed_amount,
      currency: values.currency,
      dates: values.dates,
      requested_outcome: values.requested_outcome,
      narrative: values.narrative.trim(),
      follow_up_answers: buildFollowUpAnswers(),
    };

    setSubmitting(true);
    setErrors({});
    setGeneralError(null);
    try {
      const result = await onSubmit(claim);
      if (!result.ok) {
        const fieldMap: Record<string, string> = {};
        const general: string[] = [];
        for (const fe of result.fieldErrors) {
          const key = normalizeFieldKey(fe.field);
          if (key === "general") general.push(fe.message);
          else fieldMap[key] = fe.message;
        }
        setErrors(fieldMap);
        setGeneralError(result.message ?? (general.length > 0 ? general.join(" ") : null));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={(e) => void handleSubmit(e)} noValidate>
      {generalError && (
        <p role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
          {generalError}
        </p>
      )}

      <FormField label="Type de dossier" error={errors.case_type} followUp={followUpFor("case_type")} required>
        {(fieldProps) => (
          <select
            {...fieldProps}
            value={values.case_type}
            onChange={(e) => setValues((prev) => ({ ...prev, case_type: e.target.value }))}
            className={CONTROL_CLASSES}
          >
            <option value="">Sélectionnez…</option>
            {config.case_types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        )}
      </FormField>

      <FormField
        label="Nom du demandeur (créancier)"
        error={errors.claimant_name}
        followUp={followUpFor("claimant_name")}
        required
      >
        {(fieldProps) => (
          <input
            {...fieldProps}
            type="text"
            maxLength={200}
            value={values.claimant_name}
            onChange={(e) => setValues((prev) => ({ ...prev, claimant_name: e.target.value }))}
            className={CONTROL_CLASSES}
          />
        )}
      </FormField>

      <FormField
        label="Nom de la partie adverse"
        error={errors.counterparty_name}
        followUp={followUpFor("counterparty_name")}
        required
      >
        {(fieldProps) => (
          <input
            {...fieldProps}
            type="text"
            maxLength={200}
            value={values.counterparty_name}
            onChange={(e) => setValues((prev) => ({ ...prev, counterparty_name: e.target.value }))}
            className={CONTROL_CLASSES}
          />
        )}
      </FormField>

      <div className="grid grid-cols-2 gap-4">
        <FormField
          label="Montant réclamé"
          error={errors.claimed_amount}
          followUp={followUpFor("claimed_amount")}
          hint="Ex. 20000.500 ou 20000,500"
          required
        >
          {(fieldProps) => (
            <input
              {...fieldProps}
              type="text"
              inputMode="decimal"
              value={values.claimed_amount}
              onChange={(e) => setValues((prev) => ({ ...prev, claimed_amount: e.target.value }))}
              className={`${CONTROL_CLASSES} tabular`}
            />
          )}
        </FormField>

        <FormField label="Devise" error={errors.currency} followUp={followUpFor("currency")} required>
          {(fieldProps) => (
            <select
              {...fieldProps}
              value={values.currency}
              onChange={(e) => setValues((prev) => ({ ...prev, currency: e.target.value }))}
              className={CONTROL_CLASSES}
            >
              <option value="">Sélectionnez…</option>
              {config.currencies.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </select>
          )}
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {DATE_FIELD_KEYS.map((key) => (
          <FormField
            key={key}
            label={`${DATE_LABELS[key]} (si connue)`}
            followUp={followUpFor(`dates.${key}`)}
            hint="Laissez vide si la date est inconnue."
          >
            {(fieldProps) => (
              <input
                {...fieldProps}
                type="date"
                value={values.dates[key] ?? ""}
                onChange={(e) => setDate(key, e.target.value)}
                className={`${CONTROL_CLASSES} tabular`}
              />
            )}
          </FormField>
        ))}
      </div>

      <FormField
        label="Résultat demandé"
        error={errors.requested_outcome}
        followUp={followUpFor("requested_outcome")}
        required
      >
        {(fieldProps) => (
          <select
            {...fieldProps}
            value={values.requested_outcome}
            onChange={(e) => setValues((prev) => ({ ...prev, requested_outcome: e.target.value }))}
            className={CONTROL_CLASSES}
          >
            <option value="">Sélectionnez…</option>
            {config.requested_outcomes.map((outcome) => (
              <option key={outcome} value={outcome}>
                {outcome}
              </option>
            ))}
          </select>
        )}
      </FormField>

      <FormField
        label="Description de la transaction"
        error={errors.narrative}
        followUp={followUpFor("narrative")}
        hint={`${values.narrative.trim().length} / 4000 caractères (30 minimum)`}
        required
      >
        {(fieldProps) => (
          <textarea
            {...fieldProps}
            rows={5}
            maxLength={4000}
            value={values.narrative}
            onChange={(e) => setValues((prev) => ({ ...prev, narrative: e.target.value }))}
            className={CONTROL_CLASSES}
          />
        )}
      </FormField>

      {unanchoredQuestions.length > 0 && (
        <fieldset className="flex flex-col gap-4 rounded-md border border-border bg-surface-muted p-4">
          <legend className="px-1 text-sm font-medium text-text">Informations complémentaires</legend>
          <p className="text-sm text-text-muted">
            Quelques précisions supplémentaires nous aideraient à préparer votre dossier.
          </p>
          {unanchoredQuestions.map((q) => (
            <FormField key={q.id} label={q.message}>
              {(fieldProps) => (
                <input
                  {...fieldProps}
                  type="text"
                  maxLength={1000}
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                  className={CONTROL_CLASSES}
                />
              )}
            </FormField>
          ))}
        </fieldset>
      )}

      <div className="flex items-center gap-3 border-t border-border pt-4">
        <Button type="submit" icon={<FloppyDisk size={15} />} pending={submitting}>
          {submitting ? "Enregistrement…" : submitLabel}
        </Button>
        <p className="text-xs text-text-subtle">Les champs marqués d'une astérisque sont obligatoires.</p>
      </div>
    </form>
  );
}
