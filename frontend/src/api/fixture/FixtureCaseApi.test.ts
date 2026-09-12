import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../ApiError";
import { FIXTURE_DEMO_PASSWORD, FIXTURE_USERS } from "./seed";
import { FixtureCaseApi } from "./FixtureCaseApi";

describe("FixtureCaseApi", () => {
  let api: FixtureCaseApi;

  beforeEach(() => {
    api = new FixtureCaseApi();
  });

  it("returns config without requiring auth", async () => {
    const config = await api.getConfig();
    expect(config.case_types).toContain("unpaid_goods_invoice");
    expect(config.execution_mode).toBe("fixture");
  });

  it("rejects getCurrentUser before login", async () => {
    await expect(api.getCurrentUser()).resolves.toBeNull();
  });

  it("logs a seeded account in and restores it via getCurrentUser", async () => {
    const preparer = FIXTURE_USERS.find((u) => u.role === "preparer")!;
    const session = await api.login(preparer.email, FIXTURE_DEMO_PASSWORD);
    expect(session.user.email).toBe(preparer.email);
    expect(session.csrf_token).toBeTruthy();

    const restored = await api.getCurrentUser();
    expect(restored?.user.email).toBe(preparer.email);
  });

  it("rejects an invalid password", async () => {
    const preparer = FIXTURE_USERS[0];
    await expect(api.login(preparer.email, "wrong-password")).rejects.toBeInstanceOf(ApiError);
  });

  it("logout clears the session so getCurrentUser returns null again", async () => {
    const preparer = FIXTURE_USERS[0];
    await api.login(preparer.email, FIXTURE_DEMO_PASSWORD);
    await api.logout();
    await expect(api.getCurrentUser()).resolves.toBeNull();
    // Every case-scoped call must now fail closed rather than leaking prior-user data.
    await expect(api.listCases()).rejects.toMatchObject({ status: 401 });
  });

  it("seeds the demo case (P6: 20,000 TND unpaid_goods_invoice) for its owning preparer", async () => {
    await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
    const { items } = await api.listCases();
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      case_type: "unpaid_goods_invoice",
      claimed_amount: "20000.000",
      currency: "TND",
    });
  });
});
