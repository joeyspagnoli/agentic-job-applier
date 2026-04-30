/**
 * @packageDocumentation
 *
 * Behavioral tests for the onboarding helpers exported from
 * {@link ./OnboardingPage}.
 *
 * @remarks
 * The handoff identified four bugs (2, 3, 4, 5). This file pins down the
 * pure helpers that drive the fixes for bugs 4 and 5:
 *
 * - {@link buildFiltersYaml} — bug 5: must emit a `soft_filters` block whose
 *   `positive_keywords` entries come from `roles.strongestAreas`.
 * - {@link validateGreenhouseSlug} — bug 4: must classify Greenhouse board
 *   slugs by HTTP status and never throw on network failure.
 * - {@link saveWatchlistCompanies} — bug 4: must validate every guessed slug,
 *   still write the entry even when validation fails, and return the display
 *   names of the unverified companies for surfacing to the UI.
 *
 * The integration test for `handleFinish` (bug 2) is intentionally NOT in
 * this file — it requires rendering the full wizard component and would
 * need its own `OnboardingPage.integration.test.tsx`. See the test summary
 * for the explicit gap.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildFiltersYaml,
  buildWatchlistWarning,
  saveWatchlistCompanies,
  validateGreenhouseSlug,
  type FiltersDraft,
  type RolesDraft,
  type WatchlistSaveResult,
} from "@/pages/OnboardingPage";

/**
 * Build a baseline empty filters draft with all booleans cleared and all
 * string fields empty.
 *
 * @returns Fresh filters draft suitable for use as a test starting point.
 */
function emptyFiltersDraft(): FiltersDraft {
  return {
    minSalary: "",
    maxSalary: "",
    requireRemote: false,
    jobTypes: [],
    excludeTitlePatterns: "",
    excludeCompanies: "",
  };
}

/**
 * Build a baseline empty roles draft.
 *
 * @returns Fresh roles draft suitable for use as a test starting point.
 */
function emptyRolesDraft(): RolesDraft {
  return {
    targetRoles: "",
    strongestAreas: "",
    experienceHighlights: "",
    searchTerms: "",
  };
}

/**
 * Build a fetch Response stand-in with the given status and an empty body.
 *
 * @param status - HTTP status code to use for the mock response.
 * @returns A real `Response` instance suitable for `fetch` mocks.
 */
function makeResponse(status: number): Response {
  return new Response("", { status });
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ─── buildFiltersYaml ──────────────────────────────────────────────────────

describe("buildFiltersYaml", () => {
  it("emits a hard_filters block followed by a soft_filters block", () => {
    // Arrange
    const filters = emptyFiltersDraft();
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    const hardIndex = yaml.indexOf("hard_filters:");
    const softIndex = yaml.indexOf("soft_filters:");
    expect(hardIndex).toBeGreaterThanOrEqual(0);
    expect(softIndex).toBeGreaterThan(hardIndex);
  });

  it("populates soft_filters.positive_keywords from roles.strongestAreas, one per non-blank line", () => {
    // Arrange
    const filters = emptyFiltersDraft();
    const roles: RolesDraft = {
      ...emptyRolesDraft(),
      strongestAreas: "python\nReact\n  \nKubernetes\n",
    };

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain("  positive_keywords:\n");
    expect(yaml).toContain('    - "python"');
    expect(yaml).toContain('    - "React"');
    expect(yaml).toContain('    - "Kubernetes"');
  });

  it("emits positive_keywords as an empty list when strongestAreas is empty", () => {
    // Arrange
    const filters = emptyFiltersDraft();
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert — the key must exist with no entries before negative_keywords
    expect(yaml).toContain("  positive_keywords:\n  negative_keywords:");
  });

  it("emits positive_keywords as an empty list when strongestAreas is whitespace-only", () => {
    // Arrange
    const filters = emptyFiltersDraft();
    const roles: RolesDraft = {
      ...emptyRolesDraft(),
      strongestAreas: "   \n\t\n  \n",
    };

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain("  positive_keywords:\n  negative_keywords:");
  });

  it("always writes the six hardcoded negative_keywords entries", () => {
    // Arrange
    const filters = emptyFiltersDraft();
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert — every expected entry must be present verbatim
    const expectedNegatives = [
      '    - "clearance required"',
      '    - "security clearance"',
      '    - "5+ years"',
      '    - "7+ years"',
      '    - "help desk"',
      '    - "it support"',
    ];
    for (const entry of expectedNegatives) {
      expect(yaml).toContain(entry);
    }
  });

  it("coerces non-numeric salary input to 0", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      minSalary: "not a number",
      maxSalary: "",
    };
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain("  min_salary_usd: 0");
    expect(yaml).toContain("  max_salary_usd: 0");
  });

  it("preserves numeric salary values", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      minSalary: "120000",
      maxSalary: "200000",
    };
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain("  min_salary_usd: 120000");
    expect(yaml).toContain("  max_salary_usd: 200000");
  });

  it("prefixes user-supplied exclude title patterns with (?i) for case-insensitive matching", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      excludeTitlePatterns: "intern\nDirector",
    };
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain('    - "(?i)intern"');
    expect(yaml).toContain('    - "(?i)Director"');
  });

  it("emits exclude_companies entries verbatim, preserving the user's casing", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      excludeCompanies: "Acme Corp\n   \nInitech",
    };
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain('    - "Acme Corp"');
    expect(yaml).toContain('    - "Initech"');
  });

  it("emits require_remote: true when the draft toggle is on", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      requireRemote: true,
    };
    const roles = emptyRolesDraft();

    // Act
    const yaml = buildFiltersYaml(filters, roles);

    // Assert
    expect(yaml).toContain("  require_remote: true");
  });
});

// ─── validateGreenhouseSlug ────────────────────────────────────────────────

describe("validateGreenhouseSlug", () => {
  it("returns 'verified' for an HTTP 200 response", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));

    // Act
    const result = await validateGreenhouseSlug("qualcomm");

    // Assert
    expect(result).toBe("verified");
  });

  it("returns 'not_found' for an HTTP 404 response", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));

    // Act
    const result = await validateGreenhouseSlug("thiswillneverexist99");

    // Assert
    expect(result).toBe("not_found");
  });

  it("returns 'not_found' for an HTTP 500 response", async () => {
    // Arrange — non-2xx responses other than the documented 404 are still
    // treated as "we got an answer and the slug isn't usable", not as
    // network failures (a 500 reached the server).
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(500));

    // Act
    const result = await validateGreenhouseSlug("anything");

    // Assert
    expect(result).toBe("not_found");
  });

  it("returns 'network_error' when fetch rejects and never re-throws", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network down"));

    // Act
    const result = await validateGreenhouseSlug("anything");

    // Assert
    expect(result).toBe("network_error");
  });

  it("URL-encodes the slug before issuing the request", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));

    // Act
    await validateGreenhouseSlug("weird slug/with chars");

    // Assert
    const calledUrl = fetchSpy.mock.calls[0]?.[0];
    expect(typeof calledUrl).toBe("string");
    expect(calledUrl).toContain("weird%20slug%2Fwith%20chars");
  });
});

// ─── saveWatchlistCompanies ────────────────────────────────────────────────

describe("saveWatchlistCompanies", () => {
  it("returns empty buckets and never writes when input is empty", async () => {
    // Arrange
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "" });

    // Act
    const result = await saveWatchlistCompanies("", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual([]);
    expect(updateSources).not.toHaveBeenCalled();
    expect(fetchSources).not.toHaveBeenCalled();
  });

  it("returns empty buckets and never writes when input is whitespace-only", async () => {
    // Arrange
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "" });

    // Act
    const result = await saveWatchlistCompanies("   \n\t\n  ", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual([]);
    expect(updateSources).not.toHaveBeenCalled();
  });

  it("returns empty buckets when every slug resolves to HTTP 200", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Stripe\nNotion", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual([]);
    expect(updateSources).toHaveBeenCalledOnce();
  });

  it("places a 404'd company in unverified, not networkFailures", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Bogus Inc", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual(["Bogus Inc"]);
    expect(result.networkFailures).toEqual([]);
  });

  it("places a network-failed company in networkFailures, not unverified", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual(["Stripe"]);
  });

  it("partitions a mixed batch into the correct buckets", async () => {
    // Arrange — first call 200, second call 404, third call rejects
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockResolvedValueOnce(makeResponse(200));
    fetchSpy.mockResolvedValueOnce(makeResponse(404));
    fetchSpy.mockRejectedValueOnce(new TypeError("offline"));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies(
      "Verified Co\nUnverified Co\nOffline Co",
      updateSources,
      fetchSources,
    );

    // Assert
    expect(result.unverified).toEqual(["Unverified Co"]);
    expect(result.networkFailures).toEqual(["Offline Co"]);
  });

  it("still writes every entry — verified, 404, or network failure — to sources YAML", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockResolvedValueOnce(makeResponse(200));
    fetchSpy.mockResolvedValueOnce(makeResponse(404));
    fetchSpy.mockRejectedValueOnce(new TypeError("offline"));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies(
      "Verified Co\nUnverified Co\nOffline Co",
      updateSources,
      fetchSources,
    );

    // Assert
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("  Verified Co:");
    expect(writtenYaml).toContain("  Unverified Co:");
    expect(writtenYaml).toContain("  Offline Co:");
    expect(writtenYaml).toContain('    greenhouse_id: "verifiedco"');
    expect(writtenYaml).toContain('    greenhouse_id: "unverifiedco"');
    expect(writtenYaml).toContain('    greenhouse_id: "offlineco"');
  });

  it("appends a new greenhouse_companies block when the existing YAML has none", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "other_section: []\n" });

    // Act
    await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("other_section: []");
    expect(writtenYaml).toContain("greenhouse_companies:\n");
    expect(writtenYaml).toContain("  Stripe:");
  });

  it("inserts entries directly under an existing greenhouse_companies header", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({
      yaml_text: "greenhouse_companies:\n  Existing:\n    greenhouse_id: \"existing\"\n",
    });

    // Act
    await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert — new entry appears between the header and the previously-existing entry
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    const headerIndex = writtenYaml.indexOf("greenhouse_companies:");
    const stripeIndex = writtenYaml.indexOf("  Stripe:");
    const existingIndex = writtenYaml.indexOf("  Existing:");
    expect(headerIndex).toBeGreaterThanOrEqual(0);
    expect(stripeIndex).toBeGreaterThan(headerIndex);
    expect(existingIndex).toBeGreaterThan(stripeIndex);
  });

  it("escapes double-quotes in the company display name when written as a quoted YAML key", async () => {
    // Arrange — a company name containing `"` forces the writer down the
    // quoted-key branch (plain keys reject quote characters).
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies('Acme "Quoted" Co', updateSources, fetchSources);

    // Assert — the embedded quotes must be backslash-escaped, not raw
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain('  "Acme \\"Quoted\\" Co":');
  });
});

// ─── YAML escaping (regression coverage for the quote-injection bug) ───────

describe("buildFiltersYaml YAML-escape regression coverage", () => {
  it("backslash-escapes double-quotes in exclude_companies entries", () => {
    // Arrange
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      excludeCompanies: 'Acme "Quoted" Co',
    };

    // Act
    const yaml = buildFiltersYaml(filters, emptyRolesDraft());

    // Assert
    expect(yaml).toContain('    - "Acme \\"Quoted\\" Co"');
    expect(yaml).not.toContain('    - "Acme "Quoted" Co"');
  });

  it("backslash-escapes backslashes in exclude_title_patterns", () => {
    // Arrange — a stray backslash in a regex would otherwise become an
    // unterminated YAML escape sequence.
    const filters: FiltersDraft = {
      ...emptyFiltersDraft(),
      excludeTitlePatterns: "weird\\path",
    };

    // Act
    const yaml = buildFiltersYaml(filters, emptyRolesDraft());

    // Assert
    expect(yaml).toContain('    - "(?i)weird\\\\path"');
  });

  it("escapes double-quotes in positive_keywords entries", () => {
    // Arrange
    const roles: RolesDraft = {
      ...emptyRolesDraft(),
      strongestAreas: 'C++ "advanced"\nKubernetes',
    };

    // Act
    const yaml = buildFiltersYaml(emptyFiltersDraft(), roles);

    // Assert
    expect(yaml).toContain('    - "C++ \\"advanced\\""');
    expect(yaml).toContain('    - "Kubernetes"');
  });
});

// ─── buildWatchlistWarning ─────────────────────────────────────────────────

describe("buildWatchlistWarning", () => {
  it("returns null when both buckets are empty", () => {
    // Arrange
    const result: WatchlistSaveResult = { unverified: [], networkFailures: [] };

    // Act
    const message = buildWatchlistWarning(result);

    // Assert
    expect(message).toBeNull();
  });

  it("formats only the unverified sentence when there are no network failures", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme", "Initech"],
      networkFailures: [],
    };

    // Act
    const message = buildWatchlistWarning(result);

    // Assert
    expect(message).not.toBeNull();
    expect(message).toContain("Could not verify Greenhouse IDs for: Acme, Initech");
    expect(message).not.toContain("Could not reach Greenhouse");
    expect(message).toContain("Redirecting…");
  });

  it("formats only the network-failure sentence when there are no unverified slugs", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: ["Stripe"],
    };

    // Act
    const message = buildWatchlistWarning(result);

    // Assert
    expect(message).not.toBeNull();
    expect(message).toContain("Could not reach Greenhouse to verify: Stripe");
    expect(message).not.toContain("Could not verify Greenhouse IDs");
    expect(message).toContain("Redirecting…");
  });

  it("includes both sentences when both buckets are non-empty", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: ["Stripe"],
    };

    // Act
    const message = buildWatchlistWarning(result);

    // Assert
    expect(message).not.toBeNull();
    expect(message).toContain("Could not verify Greenhouse IDs for: Acme");
    expect(message).toContain("Could not reach Greenhouse to verify: Stripe");
  });
});
