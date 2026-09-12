import { describe, expect, it } from "vitest";
import { normalizeClaimedAmount } from "./amount";

describe("normalizeClaimedAmount", () => {
  it("accepts an already-canonical decimal string unchanged", () => {
    expect(normalizeClaimedAmount("20000.500")).toEqual({ ok: true, value: "20000.500" });
  });

  it("accepts an integer with no fractional part", () => {
    expect(normalizeClaimedAmount("20000")).toEqual({ ok: true, value: "20000" });
  });

  it("converts an unambiguous French comma to a dot", () => {
    expect(normalizeClaimedAmount("20000,500")).toEqual({ ok: true, value: "20000.500" });
  });

  it("rejects a comma that could be a thousands separator", () => {
    const result = normalizeClaimedAmount("1,000");
    expect(result.ok).toBe(false);
  });

  it("rejects mixed dot-and-comma input as ambiguous", () => {
    const result = normalizeClaimedAmount("20.000,5");
    expect(result.ok).toBe(false);
  });

  it("rejects more than 12 integer digits", () => {
    const result = normalizeClaimedAmount("1234567890123");
    expect(result.ok).toBe(false);
  });

  it("rejects more than 3 fractional digits", () => {
    const result = normalizeClaimedAmount("100.1234");
    expect(result.ok).toBe(false);
  });

  it("rejects a negative amount", () => {
    const result = normalizeClaimedAmount("-500");
    expect(result.ok).toBe(false);
  });

  it("rejects an empty amount", () => {
    const result = normalizeClaimedAmount("   ");
    expect(result.ok).toBe(false);
  });

  it("never rounds through floating point — a long exact value keeps every digit", () => {
    const result = normalizeClaimedAmount("123456789012.123");
    expect(result).toEqual({ ok: true, value: "123456789012.123" });
  });

  it("never rounds through floating point on the comma path either", () => {
    const result = normalizeClaimedAmount("123456789012,123");
    expect(result).toEqual({ ok: true, value: "123456789012.123" });
  });
});
