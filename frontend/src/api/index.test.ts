import { describe, expect, it } from "vitest";
import { resolveDataMode } from "./index";

describe("resolveDataMode", () => {
  it("defaults to fixture when unset", () => {
    expect(resolveDataMode(undefined)).toBe("fixture");
  });

  it("accepts fixture and http", () => {
    expect(resolveDataMode("fixture")).toBe("fixture");
    expect(resolveDataMode("http")).toBe("http");
  });

  it("throws on an unknown mode instead of silently falling back", () => {
    expect(() => resolveDataMode("live")).toThrow(/Unknown VITE_DATA_MODE/);
  });
});
