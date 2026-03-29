import { describe, expect, it } from "vitest";

import { shouldInvalidateOnSync } from "@/components/layout/topbar-sync";

describe("shouldInvalidateOnSync", () => {
  it("returns false for settings queries", () => {
    expect(shouldInvalidateOnSync("settings")).toBe(false);
  });

  it("returns true for non-settings queries", () => {
    expect(shouldInvalidateOnSync("jobs")).toBe(true);
    expect(shouldInvalidateOnSync("dashboard")).toBe(true);
  });

  it("returns true for unknown query-key roots", () => {
    expect(shouldInvalidateOnSync(undefined)).toBe(true);
    expect(shouldInvalidateOnSync(42)).toBe(true);
  });
});
