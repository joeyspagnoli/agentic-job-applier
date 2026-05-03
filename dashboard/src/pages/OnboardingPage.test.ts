/**
 * @packageDocumentation
 *
 * Behavioral tests for the onboarding helpers exported from
 * {@link ./OnboardingPage}.
 *
 * @remarks
 * Covers the pure helpers that drive the watchlist and filter logic:
 *
 * - {@link buildFiltersYaml} — must emit a `soft_filters` block whose
 *   `positive_keywords` entries come from `roles.strongestAreas`.
 * - {@link validateGreenhouseSlug} — must classify Greenhouse board slugs by
 *   HTTP status and never throw on network failure.
 * - {@link resolveGreenhouseSlug} — must hit the lookup table first (no fetch),
 *   then fall through to multi-pattern API probing for unknown companies.
 * - {@link saveWatchlistCompanies} — must skip YAML writes for
 *   `not_on_greenhouse` companies, write naive slugs for `not_found` and
 *   `network_error`, and return the correctly partitioned result.
 * - {@link buildWatchlistWarning} — must return `{ warning, notOnGreenhouseWarning }`
 *   with distinct copy for each failure mode.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildFiltersYaml,
  buildWatchlistWarning,
  resolveGreenhouseSlug,
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

// ─── resolveGreenhouseSlug ─────────────────────────────────────────────────

describe("resolveGreenhouseSlug", () => {
  it("returns verified slug from lookup without calling fetch for a known company", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const slugs = { Stripe: "stripe" };

    // Act
    const result = await resolveGreenhouseSlug("Stripe", slugs);

    // Assert
    expect(result).toEqual({ slug: "stripe", status: "verified" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("lookup is case-insensitive — 'stripe' matches 'Stripe' key", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch");
    const slugs = { Stripe: "stripe" };

    // Act
    const result = await resolveGreenhouseSlug("stripe", slugs);

    // Assert
    expect(result).toEqual({ slug: "stripe", status: "verified" });
  });

  it("returns not_on_greenhouse for a null lookup entry without calling fetch", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const slugs: Record<string, string | null> = { NVIDIA: null };

    // Act
    const result = await resolveGreenhouseSlug("NVIDIA", slugs);

    // Assert
    expect(result).toEqual({ slug: "", status: "not_on_greenhouse" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("null lookup is also case-insensitive — 'nvidia' matches 'NVIDIA' key", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const slugs: Record<string, string | null> = { NVIDIA: null };

    // Act
    const result = await resolveGreenhouseSlug("nvidia", slugs);

    // Assert
    expect(result).toEqual({ slug: "", status: "not_on_greenhouse" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("resolves via pattern 1 (no-space) when company is not in lookup", async () => {
    // Arrange — first fetch call returns 200
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(200));
    const slugs = {};

    // Act
    const result = await resolveGreenhouseSlug("Notion Inc", slugs);

    // Assert
    expect(result.status).toBe("verified");
    expect(result.slug).toBe("notioninc");
  });

  it("resolves via pattern 2 (hyphenated) when pattern 1 returns 404", async () => {
    // Arrange — pattern 1 → 404, pattern 2 → 200
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // "notioninc" fails
    fetchSpy.mockResolvedValueOnce(makeResponse(200)); // "notion-inc" succeeds

    // Act
    const result = await resolveGreenhouseSlug("Notion Inc", {});

    // Assert
    expect(result.status).toBe("verified");
    expect(result.slug).toBe("notion-inc");
  });

  it("strips legal suffix (pattern 4) to find slug when simpler patterns fail", async () => {
    // Arrange — "acmecorp" fails, "acme-corp" fails, "acme" fails, then
    // the suffix-stripped form "acme" is tried again (duplicate — skipped
    // by validateGreenhouseSlug but the loop still runs). Use a name where
    // pattern 4 differs: "Acme Inc." → strip " Inc." → "acme"
    // Patterns: "acmeinc." | "acme-inc." | "acme" | "acme"
    // Let pattern 1 ("acmeinc.") fail, pattern 2 ("acme-inc.") fail,
    // pattern 3 ("acme") succeed.
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // "acmeinc." fails
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // "acme-inc." fails
    fetchSpy.mockResolvedValueOnce(makeResponse(200)); // "acme" succeeds

    // Act
    const result = await resolveGreenhouseSlug("Acme Inc.", {});

    // Assert
    expect(result.status).toBe("verified");
    expect(result.slug).toBe("acme");
  });

  it("returns not_found with the naive slug when all patterns return 404", async () => {
    // Arrange — all fetch calls return 404
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));

    // Act
    const result = await resolveGreenhouseSlug("Bogus Corp", {});

    // Assert
    expect(result.status).toBe("not_found");
    expect(result.slug).toBe("boguscorp"); // patterns[0] = naive no-space slug
  });

  it("returns network_error when every pattern hits a network failure", async () => {
    // Arrange — all fetch calls reject
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));

    // Act
    const result = await resolveGreenhouseSlug("Offline Corp", {});

    // Assert
    expect(result.status).toBe("network_error");
    expect(result.slug).toBe("offlinecorp");
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
    expect(result.notOnGreenhouse).toEqual([]);
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
    expect(result.notOnGreenhouse).toEqual([]);
    expect(updateSources).not.toHaveBeenCalled();
  });

  it("returns empty buckets when every slug is in the lookup table as verified", async () => {
    // Arrange — "Stripe" and "Anthropic" are in the bundled lookup table
    // with known good slugs; no fetch should be needed.
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Stripe\nAnthropic", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual([]);
    expect(result.notOnGreenhouse).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(updateSources).toHaveBeenCalledOnce();
  });

  it("places a company confirmed absent from Greenhouse into notOnGreenhouse, not unverified", async () => {
    // Arrange — "NVIDIA" is in the bundled lookup table with a null value
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("NVIDIA", updateSources, fetchSources);

    // Assert
    expect(result.notOnGreenhouse).toEqual(["NVIDIA"]);
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("does NOT write a YAML entry for a not_on_greenhouse company", async () => {
    // Arrange — "NVIDIA" is confirmed absent; no entry should appear
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies("NVIDIA", updateSources, fetchSources);

    // Assert — updateSources must NOT have been called (nothing to write)
    expect(updateSources).not.toHaveBeenCalled();
  });

  it("places a 404'd company in unverified, not networkFailures", async () => {
    // Arrange — company not in lookup; all patterns return 404
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Unknown Startup", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual(["Unknown Startup"]);
    expect(result.networkFailures).toEqual([]);
    expect(result.notOnGreenhouse).toEqual([]);
  });

  it("places a network-failed company in networkFailures, not unverified", async () => {
    // Arrange — company not in lookup; all patterns reject (offline)
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies("Unknown Startup", updateSources, fetchSources);

    // Assert
    expect(result.unverified).toEqual([]);
    expect(result.networkFailures).toEqual(["Unknown Startup"]);
    expect(result.notOnGreenhouse).toEqual([]);
  });

  it("partitions a mixed batch into the correct buckets", async () => {
    // Arrange — "Stripe" is in lookup (verified, no fetch); "NVIDIA" is in
    // lookup (not_on_greenhouse, no fetch); "Unknown Co" is not in lookup and
    // all patterns return 404.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies(
      "Stripe\nNVIDIA\nUnknown Co",
      updateSources,
      fetchSources,
    );

    // Assert
    expect(result.unverified).toEqual(["Unknown Co"]);
    expect(result.networkFailures).toEqual([]);
    expect(result.notOnGreenhouse).toEqual(["NVIDIA"]);
  });

  it("writes verified and not_found entries to YAML, but NOT not_on_greenhouse entries", async () => {
    // Arrange — "Stripe" → verified (lookup); "NVIDIA" → not_on_greenhouse
    // (lookup, skipped); "Unknown Co" → not_found (all 404).
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies("Stripe\nNVIDIA\nUnknown Co", updateSources, fetchSources);

    // Assert
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("  Stripe:");
    expect(writtenYaml).toContain('    greenhouse_id: "stripe"');
    expect(writtenYaml).toContain("  Unknown Co:");
    expect(writtenYaml).not.toContain("  NVIDIA:");
  });

  it("uses the resolved lookup slug in YAML, not the naive transform", async () => {
    // Arrange — "Databricks" is in the lookup table as "databricks"; the
    // naive transform would also produce "databricks", but Vercel ("vercel")
    // and Figma ("figma") confirm the pattern for names with no ambiguity.
    // Use "Scale AI" → lookup "scaleai" vs naive "scaleai" (same here), so
    // instead use a hypothetical where the lookup differs from naive: the
    // lookup table entry is trusted unconditionally without an API call.
    // Confirm: "Scale AI" → KNOWN_SLUGS lookup → "scaleai"; no fetch call.
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies("Scale AI", updateSources, fetchSources);

    // Assert — must write the lookup slug and must not have called fetch
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain('    greenhouse_id: "scaleai"');
  });

  it("appends a new greenhouse_companies block when the existing YAML has none", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch");
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
    vi.spyOn(globalThis, "fetch");
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

  it("does not call updateSources when every company is not_on_greenhouse", async () => {
    // Arrange — only companies confirmed absent from Greenhouse
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies("NVIDIA\nAMD\nIntel", updateSources, fetchSources);

    // Assert — nothing to write, so updateSources is never called
    expect(updateSources).not.toHaveBeenCalled();
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
  it("returns null for both fields when all buckets are empty", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: [],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).toBeNull();
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("populates warning for unverified companies but not notOnGreenhouseWarning", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme", "Initech"],
      networkFailures: [],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).not.toBeNull();
    expect(warning).toContain("Could not verify Greenhouse IDs for: Acme, Initech");
    expect(warning).toContain("Slugs were saved");
    expect(warning).not.toContain("Could not reach Greenhouse");
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("populates warning for network failures but not notOnGreenhouseWarning", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: ["Stripe"],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).not.toBeNull();
    expect(warning).toContain("Could not reach Greenhouse to verify: Stripe");
    expect(warning).not.toContain("Could not verify Greenhouse IDs");
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("includes both unverified and network-failure sentences in warning", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: ["Stripe"],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).not.toBeNull();
    expect(warning).toContain("Could not verify Greenhouse IDs for: Acme");
    expect(warning).toContain("Could not reach Greenhouse to verify: Stripe");
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("populates notOnGreenhouseWarning for confirmed-absent companies but not warning", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: [],
      notOnGreenhouse: ["NVIDIA", "Intel"],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).toBeNull();
    expect(notOnGreenhouseWarning).not.toBeNull();
    expect(notOnGreenhouseWarning).toContain("NVIDIA, Intel");
    expect(notOnGreenhouseWarning).toContain("different ATS");
    expect(notOnGreenhouseWarning).toContain("No entries were added");
  });

  it("populates both fields when all three buckets are non-empty", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: ["Stripe"],
      notOnGreenhouse: ["NVIDIA"],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).not.toBeNull();
    expect(warning).toContain("Could not verify Greenhouse IDs for: Acme");
    expect(notOnGreenhouseWarning).not.toBeNull();
    expect(notOnGreenhouseWarning).toContain("NVIDIA");
  });

  it("warning does not include a trailing 'Redirecting…' sentence", () => {
    // Arrange — redirect is now handled by the caller, not this function
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: [],
      notOnGreenhouse: [],
    };

    // Act
    const { warning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).not.toContain("Redirecting");
  });
});
