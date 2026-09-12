import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SessionProvider } from "../session/SessionContext";
import { LoginPage } from "./LoginPage";

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <SessionProvider>
        <LoginPage />
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  it("renders labeled email and password fields", async () => {
    renderLoginPage();
    expect(await screen.findByLabelText("Adresse e-mail")).toBeVisible();
    expect(screen.getByLabelText("Mot de passe")).toBeVisible();
    expect(screen.getByRole("button", { name: "Se connecter" })).toBeVisible();
  });

  it("shows the fixture-only demo account hint", async () => {
    renderLoginPage();
    expect(await screen.findByText(/Comptes de démonstration \(mode fixture uniquement\)/)).toBeVisible();
  });

  it("shows a linked error message on invalid credentials", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(await screen.findByLabelText("Adresse e-mail"), "amina.preparer@example.tn");
    const passwordInput = screen.getByLabelText("Mot de passe");
    await user.type(passwordInput, "wrong-password");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Identifiants invalides.");
    await waitFor(() => expect(passwordInput).toHaveAttribute("aria-describedby", alert.id));
  });
});
