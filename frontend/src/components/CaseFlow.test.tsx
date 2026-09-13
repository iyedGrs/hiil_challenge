import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Files, ListChecks, PaperPlaneTilt, Scales } from "@phosphor-icons/react";
import type { ActivityEvent } from "../api/types";
import { ActivityDrawer } from "./ActivityDrawer";
import { CaseFlow, type FlowStep } from "./CaseFlow";

const STEPS: FlowStep[] = [
  { id: "claim", label: "Réclamation", hint: "Prêt", state: "done", icon: Scales },
  { id: "documents", label: "Pièces", hint: "3 pièces", state: "done", icon: Files },
  { id: "checks", label: "Vérifications", hint: "2 points à traiter", state: "attention", icon: ListChecks },
  { id: "submission", label: "Transmission", hint: "Pas encore transmis", state: "todo", icon: PaperPlaneTilt },
];

describe("CaseFlow", () => {
  it("marks the active step and carries each step's own state hint", () => {
    render(
      <CaseFlow steps={STEPS} activeId="checks" onSelect={vi.fn()}>
        <p>Panneau des vérifications</p>
      </CaseFlow>,
    );

    const rail = within(screen.getByRole("navigation", { name: /Étapes de préparation/ }));
    expect(rail.getByRole("button", { name: /Vérifications/ })).toHaveAttribute("aria-current", "step");
    expect(rail.getByRole("button", { name: /Réclamation/ })).not.toHaveAttribute("aria-current");
    expect(rail.getByText("2 points à traiter")).toBeInTheDocument();
    expect(screen.getByText("Panneau des vérifications")).toBeInTheDocument();
  });

  it("offers the previous and next step as the footer move, not a dead end", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <CaseFlow steps={STEPS} activeId="checks" onSelect={onSelect}>
        <p>Panneau</p>
      </CaseFlow>,
    );

    // Footer controls sit outside the rail; both name the step they lead to.
    const footer = screen.getByRole("button", { name: /^Transmission$/ });
    await user.click(footer);
    expect(onSelect).toHaveBeenCalledWith("submission");
  });

  it("blocks a step that declares a reason and explains it rather than failing on arrival", () => {
    const steps = STEPS.map((step) =>
      step.id === "submission" ? { ...step, disabledReason: "Aucune analyse publiée." } : step,
    );
    render(
      <CaseFlow steps={steps} activeId="checks" onSelect={vi.fn()}>
        <p>Panneau</p>
      </CaseFlow>,
    );

    const rail = within(screen.getByRole("navigation", { name: /Étapes de préparation/ }));
    const blocked = rail.getByRole("button", { name: /Transmission/ });
    expect(blocked).toBeDisabled();
    expect(blocked).toHaveAttribute("title", "Aucune analyse publiée.");
  });
});

const ACTIVITY: ActivityEvent[] = [
  { id: "EV_1", type: "case_created", message: "Dossier créé.", created_at: "2026-06-11T09:00:00Z" },
  {
    id: "EV_2",
    type: "reviewer_clarification_requested",
    message: "Merci de préciser la date de livraison.",
    created_at: "2026-06-13T10:00:00Z",
  },
];

describe("ActivityDrawer", () => {
  it("renders nothing until it is opened, so the log never sits in the main flow", () => {
    render(<ActivityDrawer open={false} onClose={vi.fn()} activity={ACTIVITY} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists activity newest first and closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<ActivityDrawer open onClose={onClose} activity={ACTIVITY} />);

    const dialog = screen.getByRole("dialog", { name: "Historique du dossier" });
    const entries = within(dialog).getAllByRole("listitem");
    expect(entries[0]).toHaveTextContent("Merci de préciser la date de livraison.");
    expect(entries[1]).toHaveTextContent("Dossier créé.");

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
