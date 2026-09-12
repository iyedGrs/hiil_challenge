import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AppConfig, Claim } from "../api/types";
import { IntakeForm, type IntakeFormResult } from "./IntakeForm";

const CONFIG: AppConfig = {
  case_types: ["unpaid_goods_invoice"],
  currencies: ["TND"],
  requested_outcomes: ["payment", "payment_plan"],
  limits: { max_active_files: 10, max_total_pages: 30, max_file_bytes: 1, max_case_bytes: 1 },
  legal_coverage: { unpaid_goods_invoice: "unvalidated" },
  execution_mode: "fixture",
};

const BLANK_CLAIM: Claim = {
  case_type: "unpaid_goods_invoice",
  claimant_name: "Demo Supplier",
  counterparty_name: "Demo Customer",
  claimed_amount: "20000.000",
  currency: "TND",
  dates: { contract: null, delivery: null, invoice: null, payment_due: null },
  requested_outcome: "payment",
  narrative: "Nous avons fourni du mobilier de bureau et la facture reste impayée à ce jour.",
  follow_up_answers: [],
};

describe("IntakeForm", () => {
  it("preserves every entered value when the server returns field errors (FE-02)", async () => {
    const user = userEvent.setup();
    const result: IntakeFormResult = {
      ok: false,
      fieldErrors: [{ field: "claimant_name", message: "Ce nom est déjà utilisé." }],
    };
    const onSubmit = vi.fn(async (_claim: Claim): Promise<IntakeFormResult> => result);

    render(
      <IntakeForm config={CONFIG} initialClaim={BLANK_CLAIM} questions={[]} submitLabel="Créer" onSubmit={onSubmit} />,
    );

    await user.click(screen.getByRole("button", { name: "Créer" }));

    expect(await screen.findByText("Ce nom est déjà utilisé.")).toBeVisible();
    // Every entered field is still populated after the error — nothing was cleared.
    expect(screen.getByLabelText(/Nom du demandeur/)).toHaveValue("Demo Supplier");
    expect(screen.getByLabelText(/Nom de la partie adverse/)).toHaveValue("Demo Customer");
    expect(screen.getByLabelText(/Montant réclamé/)).toHaveValue("20000.000");
    expect(screen.getByLabelText(/Description de la transaction/)).toHaveValue(BLANK_CLAIM.narrative);
  });

  it("shows a follow-up question next to its mapped field instead of a generic failure", async () => {
    render(
      <IntakeForm
        config={CONFIG}
        initialClaim={{ ...BLANK_CLAIM, narrative: "Le client n'a pas payé la facture correspondant à la commande." }}
        questions={[{ id: "describe_goods", field: "narrative", message: "Quels biens ont été fournis ?" }]}
        submitLabel="Enregistrer"
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("Quels biens ont été fournis ?")).toBeVisible();
    expect(screen.queryByText(/analyse a échoué/i)).not.toBeInTheDocument();
  });

  it("submits an unmapped follow-up question as a bounded short-answer field", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async (_claim: Claim): Promise<IntakeFormResult> => ({ ok: true }));

    render(
      <IntakeForm
        config={CONFIG}
        initialClaim={BLANK_CLAIM}
        questions={[{ id: "clarify_link", field: "invoice_contract_link", message: "Quel est le lien avec le contrat ?" }]}
        submitLabel="Enregistrer"
        onSubmit={onSubmit}
      />,
    );

    await user.type(screen.getByLabelText("Quel est le lien avec le contrat ?"), "La facture cite le contrat n°12.");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        follow_up_answers: [{ question_id: "clarify_link", answer: "La facture cite le contrat n°12." }],
      }),
    );
  });

  it("rejects an ambiguous amount client-side without calling onSubmit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <IntakeForm config={CONFIG} initialClaim={BLANK_CLAIM} questions={[]} submitLabel="Créer" onSubmit={onSubmit} />,
    );

    const amountInput = screen.getByLabelText(/Montant réclamé/);
    await user.clear(amountInput);
    await user.type(amountInput, "1,000");
    await user.click(screen.getByRole("button", { name: "Créer" }));

    expect(await screen.findByText(/pourrait être un séparateur de milliers/)).toBeVisible();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
