import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchApiKeysSettings,
  fetchBudget,
  fetchChromeStatus,
  uploadProfile,
  uploadResume,
} from "@/lib/api/client";

/**
 * Build one JSON response object for fetch-mock test scenarios.
 *
 * @param payload - Serializable payload body.
 * @returns Response with JSON body and content-type header.
 */
function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "content-type": "application/json",
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client success parsing", () => {
  it("raises typed empty-body error for successful empty responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", {
        status: 200,
        headers: {
          "content-type": "application/json",
        },
      }),
    );

    await expect(fetchBudget()).rejects.toMatchObject({
      code: "EMPTY_RESPONSE_BODY",
    });
  });

  it("raises typed invalid-format error for non-JSON successful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: {
          "content-type": "text/plain",
        },
      }),
    );

    await expect(fetchBudget()).rejects.toMatchObject({
      code: "INVALID_RESPONSE_FORMAT",
    });
  });

  it("accepts resume upload response containing only resume metadata", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        resume: {
          filename: "resume_content.yaml",
          path: "/tmp/resume_content.yaml",
          exists: true,
          size_bytes: 128,
          modified_at: "2026-03-29T00:00:00Z",
        },
      }),
    );

    const payload = await uploadResume(
      new File(["resume: []\n"], "resume_content.yaml", {
        type: "application/x-yaml",
      }),
    );

    expect(payload.ok).toBe(true);
    expect(payload.resume.filename).toBe("resume_content.yaml");
  });

  it("accepts profile upload response containing only profile metadata", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        profile: {
          filename: "candidate_profile.yaml",
          path: "/tmp/candidate_profile.yaml",
          exists: true,
          size_bytes: 256,
          modified_at: "2026-03-29T00:00:00Z",
        },
      }),
    );

    const payload = await uploadProfile(
      new File(["profile: {}\n"], "candidate_profile.yaml", {
        type: "application/x-yaml",
      }),
    );

    expect(payload.ok).toBe(true);
    expect(payload.profile.filename).toBe("candidate_profile.yaml");
  });

  it("fetches API key statuses for write-only key management", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        keys: [
          { name: "OPENAI_API_KEY", configured: true },
          { name: "ADZUNA_APP_ID", configured: false },
        ],
      }),
    );

    const payload = await fetchApiKeysSettings();

    expect(payload.ok).toBe(true);
    expect(payload.keys).toEqual([
      { name: "OPENAI_API_KEY", configured: true },
      { name: "ADZUNA_APP_ID", configured: false },
    ]);
  });

  it("fetches Chrome status with an OS hint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        reachable: true,
        checked_at: "2026-05-23T22:00:00+00:00",
        cdp_url: "http://host.docker.internal:9222",
        command_hint: "open -a Google Chrome ...",
      }),
    );

    const payload = await fetchChromeStatus("mac");

    expect(payload.reachable).toBe(true);
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/status/chrome?os=mac",
      undefined,
    );
  });

});
