import { describe, expect, it } from "vitest";

import { toSafeJobPostingUrl } from "@/pages/jobs-url";

describe("toSafeJobPostingUrl", () => {
  it("accepts https URLs", () => {
    expect(toSafeJobPostingUrl("https://example.com/jobs/1")).toBe("https://example.com/jobs/1");
  });

  it("accepts http URLs", () => {
    expect(toSafeJobPostingUrl("http://example.com/jobs/2")).toBe("http://example.com/jobs/2");
  });

  it("rejects javascript protocol URLs", () => {
    expect(toSafeJobPostingUrl("javascript:alert(1)")).toBeNull();
  });

  it("rejects data protocol URLs", () => {
    expect(toSafeJobPostingUrl("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==")).toBeNull();
  });

  it("rejects malformed URLs", () => {
    expect(toSafeJobPostingUrl("not-a-url")).toBeNull();
  });
});
