import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchApiKeysSettings,
  fetchBudget,
  restartSystemStack,
  stopSystemStack,
  updateServiceTierSetting,
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
          { name: "APIFY_API_TOKEN", configured: false },
        ],
      }),
    );

    const payload = await fetchApiKeysSettings();

    expect(payload.ok).toBe(true);
    expect(payload.keys).toEqual([
      { name: "OPENAI_API_KEY", configured: true },
      { name: "APIFY_API_TOKEN", configured: false },
    ]);
  });

  it("persists selected service tier with a typed payload", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        tier: "latex",
      }),
    );

    const payload = await updateServiceTierSetting("latex");

    expect(payload.ok).toBe(true);
    expect(payload.tier).toBe("latex");
    expect(fetchSpy).toHaveBeenCalledWith("/api/settings/service-tier", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tier: "latex" }),
    });
  });

  it("dispatches stack stop lifecycle action", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        action: "stop",
        status: "accepted",
        request_id: "request-stop",
      }),
    );

    const payload = await stopSystemStack();

    expect(payload.ok).toBe(true);
    expect(payload.action).toBe("stop");
    expect(payload.status).toBe("accepted");
    expect(fetchSpy).toHaveBeenCalledWith("/api/system/stop", { method: "POST" });
  });

  it("dispatches stack restart lifecycle action", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        action: "restart",
        status: "accepted",
        request_id: "request-restart",
      }),
    );

    const payload = await restartSystemStack();

    expect(payload.ok).toBe(true);
    expect(payload.action).toBe("restart");
    expect(payload.status).toBe("accepted");
    expect(fetchSpy).toHaveBeenCalledWith("/api/system/restart", { method: "POST" });
  });
});
