import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FIXTURE_DEMO_PASSWORD, FIXTURE_USERS } from "../api/fixture/seed";
import { SessionProvider, useSession } from "./SessionContext";

function Probe() {
  const { status, user, login, logout } = useSession();
  const preparer = FIXTURE_USERS[0];
  return (
    <div>
      <p data-testid="status">{status}</p>
      <p data-testid="user">{user?.email ?? "none"}</p>
      <button onClick={() => void login(preparer.email, FIXTURE_DEMO_PASSWORD)}>login</button>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

describe("SessionContext", () => {
  it("logout clears the authenticated user and status (FE-11)", async () => {
    const user = userEvent.setup();
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    await act(async () => {
      await user.click(screen.getByText("login"));
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent(FIXTURE_USERS[0].email);

    await act(async () => {
      await user.click(screen.getByText("logout"));
    });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });
});
