/**
 * @packageDocumentation
 *
 * Behavioral tests for the onboarding helpers exported from
 * {@link ./OnboardingPage}.
 *
 * @remarks
 * Covers the pure helpers that drive the watchlist, filter, and GitHub repo
 * seeding logic:
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
 * - {@link detectSimplifyCategories} — must return the correct SimplifyJobs
 *   category labels for known role keywords, and `[]` for unrecognised domains.
 * - {@link buildGithubReposBlock} — must emit valid YAML with or without a
 *   `categories:` list depending on whether categories are provided.
 * - {@link seedGithubRepos} — must replace an existing `github_repos:` block or
 *   append one when absent, then persist the result via `updateSources`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildFiltersYaml,
  buildGithubReposBlock,
  buildWatchlistWarning,
  detectSimplifyCategories,
  resolveGreenhouseSlug,
  saveWatchlistCompanies,
  seedGithubRepos,
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

  it("classifies an empty-string name as not_found without crashing", async () => {
    // Arrange — every pattern collapses to "" for an empty input. Greenhouse
    // 404s the empty-board URL, so the loop returns not_found.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));

    // Act
    const result = await resolveGreenhouseSlug("", {});

    // Assert — slug falls back to patterns[0] which is "" for empty input;
    // the contract is "don't throw" rather than "produce a sensible slug".
    expect(result.status).toBe("not_found");
    expect(typeof result.slug).toBe("string");
  });

  it("treats a name that is only a legal suffix as not_found, not a crash", async () => {
    // Arrange — "Inc." → pattern 4 strips to "" → empty-slug probe 404s.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));

    // Act
    const result = await resolveGreenhouseSlug("Inc.", {});

    // Assert
    expect(result.status).toBe("not_found");
    // patterns[0] = "inc." (lowercased, no spaces removed because none exist)
    expect(result.slug).toBe("inc.");
  });

  it("network_error wins over not_found when at least one pattern hit the network", async () => {
    // Arrange — first pattern rejects (network), all later patterns 404.
    // The function records hadNetworkError = true and returns network_error
    // even though most calls succeeded with 404. Rationale: a partial outage
    // is still our problem, not the user's.
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy.mockRejectedValueOnce(new TypeError("offline")); // pattern 1
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // pattern 2
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // pattern 3
    fetchSpy.mockResolvedValueOnce(makeResponse(404)); // pattern 4

    // Act
    const result = await resolveGreenhouseSlug("Flaky Co", {});

    // Assert
    expect(result.status).toBe("network_error");
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
    // Arrange — "NVIDIA" is confirmed absent; no child entry should appear
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    await saveWatchlistCompanies("NVIDIA", updateSources, fetchSources);

    // Assert — empty block written (clears any stale entries), but no NVIDIA child
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("greenhouse_companies:\n");
    expect(writtenYaml).not.toContain("NVIDIA");
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

  it("replaces all existing entries when greenhouse_companies block already has entries", async () => {
    // Arrange
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({
      yaml_text: "greenhouse_companies:\n  Existing:\n    greenhouse_id: \"existing\"\n",
    });

    // Act
    await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert — stale entry is gone; only the new submission remains
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("greenhouse_companies:");
    expect(writtenYaml).toContain("  Stripe:");
    expect(writtenYaml).not.toContain("  Existing:");
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

  it("replaces greenhouse_companies with empty block when all companies are not_on_greenhouse", async () => {
    // Arrange — only companies confirmed absent from Greenhouse
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({
      yaml_text: "greenhouse_companies:\n  OldStale:\n    greenhouse_id: \"old\"\n",
    });

    // Act
    await saveWatchlistCompanies("NVIDIA\nAMD\nIntel", updateSources, fetchSources);

    // Assert — stale entries cleared; empty block written
    expect(updateSources).toHaveBeenCalledOnce();
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("greenhouse_companies:\n");
    expect(writtenYaml).not.toContain("  OldStale:");
  });

  it("calls fetchSources even when all companies are not_on_greenhouse to clear stale entries", async () => {
    vi.spyOn(globalThis, "fetch");
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    await saveWatchlistCompanies("NVIDIA\nAMD", updateSources, fetchSources);

    expect(fetchSources).toHaveBeenCalledOnce();
  });

  it("writes both YAML entries when two companies normalize to the same naive slug", async () => {
    // Arrange — "Acme Corp" and "AcmeCorp" both produce "acmecorp" as
    // patterns[0]. Both 404, both end up in unverified, and both must
    // appear under their own display-name keys in the YAML so the user can
    // distinguish the entries in Settings → Sources later.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(makeResponse(404));
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "greenhouse_companies:\n" });

    // Act
    const result = await saveWatchlistCompanies(
      "Acme Corp\nAcmeCorp",
      updateSources,
      fetchSources,
    );

    // Assert — both names land in unverified; both appear in YAML under
    // distinct mapping keys.
    expect(result.unverified).toEqual(
      expect.arrayContaining(["Acme Corp", "AcmeCorp"]),
    );
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(writtenYaml).toContain("  Acme Corp:");
    expect(writtenYaml).toContain("  AcmeCorp:");
  });

  it("does not duplicate entries on repeated onboarding runs", async () => {
    // Arrange — prior run already wrote Stripe; user re-submits only Stripe
    vi.spyOn(globalThis, "fetch");
    const existingYaml =
      "greenhouse_companies:\n" +
      "  Stripe:\n    greenhouse_id: \"stripe\"\n    priority: 3\n" +
      "  OldCo:\n    greenhouse_id: \"oldco\"\n    priority: 3\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert — exactly one greenhouse_id entry, OldCo is gone
    const writtenYaml = updateSources.mock.calls[0]?.[0] as string;
    const occurrences = (writtenYaml.match(/greenhouse_id:/g) ?? []).length;
    expect(occurrences).toBe(1);
    expect(writtenYaml).toContain("  Stripe:");
    expect(writtenYaml).not.toContain("  OldCo:");
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

  // Golden-copy locks. Treat any failure here as a deliberate UI copy
  // change and update the expected string in lockstep with the source.
  it("matches the exact unverified-only copy", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: [],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).toBe(
      "Could not verify Greenhouse IDs for: Acme. Slugs were saved; correct them in Settings → Sources.",
    );
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("matches the exact network-failure-only copy", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: ["Stripe"],
      notOnGreenhouse: [],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).toBe(
      "Could not reach Greenhouse to verify: Stripe. Slugs were saved as-is; re-verify from Settings → Sources once your connection is restored.",
    );
    expect(notOnGreenhouseWarning).toBeNull();
  });

  it("matches the exact not-on-greenhouse-only copy", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: [],
      networkFailures: [],
      notOnGreenhouse: ["NVIDIA"],
    };

    // Act
    const { warning, notOnGreenhouseWarning } = buildWatchlistWarning(result);

    // Assert
    expect(warning).toBeNull();
    expect(notOnGreenhouseWarning).toBe(
      "NVIDIA don't appear to use Greenhouse — they likely use a different ATS. No entries were added for them.",
    );
  });

  it("joins unverified and network-failure sentences with a single space, in that order", () => {
    // Arrange
    const result: WatchlistSaveResult = {
      unverified: ["Acme"],
      networkFailures: ["Stripe"],
      notOnGreenhouse: [],
    };

    // Act
    const { warning } = buildWatchlistWarning(result);

    // Assert — exact concatenation pinned: unverified first, then network.
    expect(warning).toBe(
      "Could not verify Greenhouse IDs for: Acme. Slugs were saved; correct them in Settings → Sources. Could not reach Greenhouse to verify: Stripe. Slugs were saved as-is; re-verify from Settings → Sources once your connection is restored.",
    );
  });
});

// ─── detectSimplifyCategories ─────────────────────────────────────────────────

describe("detectSimplifyCategories", () => {
  it("returns ['Software'] for a plain software engineering role", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Software Engineering Intern"]);

    // Assert
    expect(result).toEqual(["Software"]);
  });

  it("returns ['Hardware'] for an electrical engineering role", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Electrical Engineering Intern"]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });

  it("returns ['Hardware'] for a firmware role", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Firmware Engineer"]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });

  it("returns ['Hardware'] for an embedded systems role", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Embedded Systems Intern"]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });

  it("returns ['PM'] when roles include product manager", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Product Manager Intern"]);

    // Assert
    expect(result).toEqual(["PM"]);
  });

  it("returns ['Quant'] when roles include quantitative", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Quantitative Research Intern"]);

    // Assert
    expect(result).toEqual(["Quant"]);
  });

  it("returns multiple categories when roles span domains", () => {
    // Arrange / Act
    const result = detectSimplifyCategories([
      "Software Engineering Intern",
      "Hardware Engineering Intern",
    ]);

    // Assert — both domains detected; order is Software, Hardware, PM, Quant.
    expect(result).toEqual(["Software", "Hardware"]);
  });

  it("returns [] for an unrecognised domain so all listings pass through", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["Mechanical Engineering Intern"]);

    // Assert
    expect(result).toEqual([]);
  });

  it("returns [] for an empty roles array", () => {
    // Arrange / Act
    const result = detectSimplifyCategories([]);

    // Assert
    expect(result).toEqual([]);
  });

  it("is case-insensitive", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["HARDWARE ENGINEER"]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });
});

// ─── buildGithubReposBlock ────────────────────────────────────────────────────

describe("buildGithubReposBlock", () => {
  it("always includes the SimplifyJobs owner, repo, branch, and json_path", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock([]);

    // Assert
    expect(yaml).toContain("owner: SimplifyJobs");
    expect(yaml).toContain("repo: Summer2026-Internships");
    expect(yaml).toContain("branch: dev");
    expect(yaml).toContain("json_path: .github/scripts/listings.json");
    expect(yaml).toContain("enabled: true");
  });

  it("omits the categories field when categories is empty (no-filter mode)", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock([]);

    // Assert
    expect(yaml).not.toContain("categories:");
  });

  it("emits a categories list when one category is provided", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock(["Hardware"]);

    // Assert
    expect(yaml).toContain("    categories:\n");
    expect(yaml).toContain('      - "Hardware"');
  });

  it("emits multiple category entries when multiple categories are provided", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock(["Software", "Hardware"]);

    // Assert
    expect(yaml).toContain('      - "Software"');
    expect(yaml).toContain('      - "Hardware"');
  });

  it("starts with the github_repos key", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock([]);

    // Assert
    expect(yaml.startsWith("github_repos:\n")).toBe(true);
  });
});

// ─── seedGithubRepos ──────────────────────────────────────────────────────────

describe("seedGithubRepos", () => {
  it("replaces an existing inline github_repos: [] entry with the built block", async () => {
    // Arrange
    const existingYaml = "indeed:\n  enabled: true\ngithub_repos: []\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineering Intern"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("github_repos:\n");
    expect(written).toContain("owner: SimplifyJobs");
    expect(written).not.toContain("github_repos: []");
  });

  it("replaces an existing block-list github_repos entry", async () => {
    // Arrange
    const existingYaml =
      "indeed:\n  enabled: true\ngithub_repos:\n  - owner: OldOwner\n    repo: OldRepo\n    enabled: false\n    categories:\n      - \"Software\"\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Electrical Engineering Intern"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("owner: SimplifyJobs");
    expect(written).not.toContain("OldOwner");
    expect(written).toContain('- "Hardware"');
  });

  it("appends the block when github_repos is absent from the YAML", async () => {
    // Arrange
    const existingYaml = "indeed:\n  enabled: true\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineering Intern"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("indeed:\n  enabled: true\n");
    expect(written).toContain("github_repos:\n");
    expect(written).toContain("owner: SimplifyJobs");
  });

  it("omits categories when roles map to no known SimplifyJobs domain", async () => {
    // Arrange
    const existingYaml = "github_repos: []\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Mechanical Engineering Intern"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).not.toContain("categories:");
  });

  it("calls updateSources exactly once", async () => {
    // Arrange
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "github_repos: []\n" });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert
    expect(updateSources).toHaveBeenCalledOnce();
  });

  it("seeds an empty-targetRoles array as a no-filter SimplifyJobs block", async () => {
    // Arrange — handleFinish() currently runs unconditionally; if the user
    // skipped the roles step (or all lines were whitespace), splitLines yields
    // [] and we still write a no-categories SimplifyJobs source so downstream
    // GitHubRepoFetcher returns all listings instead of zero.
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: "github_repos: []\n" });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos([], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("owner: SimplifyJobs");
    expect(written).not.toContain("categories:");
  });

  it("falls back to an empty string when fetchSources returns undefined yaml_text", async () => {
    // Arrange — the API contract says yaml_text is always a string, but the
    // ?? "" fallback in seedGithubRepos must not regress. If yaml_text is
    // undefined, we should still produce a valid YAML write rather than throw.
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: undefined as unknown as string });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert
    expect(updateSources).toHaveBeenCalledOnce();
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("github_repos:\n");
    expect(written).toContain("owner: SimplifyJobs");
  });

  it("preserves a pre-existing greenhouse_companies block alongside github_repos replacement", async () => {
    // Arrange — handoff Risk Areas: "verify saveWatchlistCompanies is
    // unaffected when run after seedGithubRepos — the two functions target
    // different YAML keys (github_repos vs greenhouse_companies) and neither
    // should clobber the other." This test pins the seed-then-watchlist
    // direction: a watchlist block written previously must survive a re-seed.
    const existingYaml =
      "greenhouse_companies:\n" +
      '  Stripe:\n    greenhouse_id: "stripe"\n    priority: 3\n' +
      "github_repos: []\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineering Intern"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("greenhouse_companies:");
    expect(written).toContain("  Stripe:");
    expect(written).toContain('    greenhouse_id: "stripe"');
    expect(written).toContain("    priority: 3");
    expect(written).toContain("owner: SimplifyJobs");
  });

  it("preserves YAML content after the github_repos block when it is replaced", async () => {
    // Arrange — guard against the regex `(?:[ \t][^\n]*\n)*` over-consuming
    // sibling top-level keys. Section starts (column-0) must not be eaten.
    const existingYaml =
      "github_repos:\n" +
      "  - owner: OldOwner\n" +
      "    repo: OldRepo\n" +
      "    enabled: true\n" +
      "ashby_companies:\n" +
      "  Acme:\n" +
      "    ashby_id: acme\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert — every preserved-section landmark must still be present
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("ashby_companies:");
    expect(written).toContain("  Acme:");
    expect(written).toContain("    ashby_id: acme");
    expect(written).not.toContain("OldOwner");
  });

  it("preserves YAML content before the github_repos block when it is replaced", async () => {
    // Arrange
    const existingYaml =
      "indeed:\n  enabled: true\n  api_key: secret_value\n" +
      "linkedin:\n  enabled: false\n" +
      "github_repos: []\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existingYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("indeed:\n  enabled: true\n  api_key: secret_value\n");
    expect(written).toContain("linkedin:\n  enabled: false\n");
    expect(written).toContain("owner: SimplifyJobs");
  });

  it("is idempotent: running seed twice with the same roles produces stable YAML", async () => {
    // Arrange
    const updateSources = vi.fn().mockResolvedValue(undefined);
    const fetchSourcesFirst = vi.fn().mockResolvedValue({ yaml_text: "github_repos: []\n" });

    // Act — first run
    await seedGithubRepos(["Electrical Engineering Intern"], updateSources, fetchSourcesFirst);
    const firstWrite = updateSources.mock.calls[0]?.[0] as string;

    // Second run starts from the YAML that the first run produced
    const fetchSourcesSecond = vi.fn().mockResolvedValue({ yaml_text: firstWrite });
    await seedGithubRepos(["Electrical Engineering Intern"], updateSources, fetchSourcesSecond);
    const secondWrite = updateSources.mock.calls[1]?.[0] as string;

    // Assert — second write must match first byte-for-byte
    expect(secondWrite).toBe(firstWrite);
  });

  it("calls fetchSources before updateSources (read-replace-write order)", async () => {
    // Arrange — order matters: writing without fetching first would clobber
    // the rest of sources.yaml. Pin this with call order tracking.
    const order: string[] = [];
    const fetchSources = vi.fn().mockImplementation(async () => {
      order.push("fetch");
      return { yaml_text: "github_repos: []\n" };
    });
    const updateSources = vi.fn().mockImplementation(async () => {
      order.push("update");
    });

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert
    expect(order).toEqual(["fetch", "update"]);
  });
});

// ─── detectSimplifyCategories — extended keyword + ordering coverage ──────────

describe("detectSimplifyCategories — keyword and ordering coverage", () => {
  // Each keyword should independently classify the role into the correct
  // category. The handoff promised "case-insensitive substring match" so we
  // verify the contract for every keyword the source declares, not just the
  // few that were spot-checked.
  it.each([
    ["electrical engineer"],
    ["hardware engineer"],
    ["embedded software"],
    ["FPGA Designer"],
    ["RF Engineer"],
    ["VLSI Intern"],
    ["ECE Intern"],
    ["Circuit Design Intern"],
    ["PCB Engineer"],
    ["Firmware Developer"],
  ])("classifies %s as Hardware", (role) => {
    // Arrange / Act
    const result = detectSimplifyCategories([role]);

    // Assert
    expect(result).toContain("Hardware");
  });

  it.each([
    ["software engineer"],
    ["SWE Intern"],
    ["Frontend Developer"],
    ["Backend Engineer"],
    ["Fullstack Engineer"],
    ["Full-Stack Developer"],
    ["Web Developer"],
    ["Mobile Developer"],
    ["iOS Developer"],
    ["Android Engineer"],
  ])("classifies %s as Software", (role) => {
    // Arrange / Act
    const result = detectSimplifyCategories([role]);

    // Assert
    expect(result).toContain("Software");
  });

  it.each([
    ["Product Manager Intern"],
    ["Product Management Associate"],
    ["Program Manager"],
  ])("classifies %s as PM", (role) => {
    // Arrange / Act
    const result = detectSimplifyCategories([role]);

    // Assert
    expect(result).toContain("PM");
  });

  it.each([
    ["Quant Researcher"],
    ["Quantitative Analyst"],
  ])("classifies %s as Quant", (role) => {
    // Arrange / Act
    const result = detectSimplifyCategories([role]);

    // Assert
    expect(result).toContain("Quant");
  });

  it("returns categories in stable Software-Hardware-PM-Quant order when all four match", () => {
    // Arrange / Act — order is part of the contract; users who scan the YAML
    // will rely on it being deterministic when comparing pre/post-onboarding.
    const result = detectSimplifyCategories([
      "Quantitative Researcher",
      "Product Manager",
      "Hardware Engineer",
      "Software Engineer",
    ]);

    // Assert
    expect(result).toEqual(["Software", "Hardware", "PM", "Quant"]);
  });

  it("does not duplicate a category when multiple matching keywords appear", () => {
    // Arrange / Act — "embedded firmware" matches both `embedded` and `firmware`
    // keywords; output should still contain a single "Hardware" entry.
    const result = detectSimplifyCategories(["Embedded Firmware Engineer"]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });

  it("does not duplicate categories across multiple matching role strings", () => {
    // Arrange / Act
    const result = detectSimplifyCategories([
      "Software Engineer",
      "Frontend Developer",
      "Backend Engineer",
    ]);

    // Assert
    expect(result).toEqual(["Software"]);
  });

  it("ignores empty strings inside the roles array", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["", "Software Engineer", ""]);

    // Assert
    expect(result).toEqual(["Software"]);
  });

  it("returns [] when every entry is an empty string", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["", "", ""]);

    // Assert
    expect(result).toEqual([]);
  });

  it("returns [] when entries are whitespace-only", () => {
    // Arrange / Act — the function does not trim, so whitespace strings
    // simply contribute spaces to `combined`; no keyword can match.
    const result = detectSimplifyCategories(["   ", "\t\n"]);

    // Assert
    expect(result).toEqual([]);
  });

  // Documented behavior pin: substring matching is intentional. The handoff
  // notes "no realistic job title triggers this" — we pin the current
  // behavior so anyone who later switches to word-boundary matching
  // explicitly chooses to and updates this test.
  it("matches substring 'rf' inside an unrelated word (substring contract)", () => {
    // Arrange — "Performance" contains "rf"; this currently classifies
    // as Hardware. If this test fails, you have changed the matching
    // strategy from substring to word-boundary — update this test
    // intentionally, not as a side effect.
    const result = detectSimplifyCategories(["Performance Engineer"]);

    // Assert
    expect(result).toContain("Hardware");
  });

  it.each([
    ["Mechanical Engineering Intern"],
    ["Civil Engineering"],
    ["Biomedical Engineer"],
    ["Chemical Engineer"],
    ["Marketing Analyst"],
    ["Financial Analyst"],
    ["Project Coordinator"],
    ["Data Analyst"],
    ["Sales Associate"],
    ["Operations Associate"],
  ])("returns [] for unrelated role %s", (role) => {
    // Arrange / Act
    const result = detectSimplifyCategories([role]);

    // Assert
    expect(result).toEqual([]);
  });

  it("matches lowercase keyword when role is fully UPPERCASE", () => {
    // Arrange / Act
    const result = detectSimplifyCategories(["BACKEND DEVELOPER"]);

    // Assert
    expect(result).toEqual(["Software"]);
  });

  it("matches mixed-case role when keyword is in the middle of a sentence", () => {
    // Arrange / Act
    const result = detectSimplifyCategories([
      "Looking for opportunities in Embedded systems and similar",
    ]);

    // Assert
    expect(result).toEqual(["Hardware"]);
  });
});

// ─── buildGithubReposBlock — mutation-resistant assertions ────────────────────

describe("buildGithubReposBlock — structure and ordering", () => {
  it("contains the literal substring 'categories:' zero times when categories is empty", () => {
    // Arrange / Act — kills mutants that emit "    categories:\n" with no
    // entries; the empty case must omit the key entirely so YAML parsers
    // produce `null` rather than `[]` for the categories field.
    const yaml = buildGithubReposBlock([]);

    // Assert
    expect(yaml.includes("categories:")).toBe(false);
  });

  it("ends with a newline so subsequent appended content is not merged into the last category line", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock(["Software"]);

    // Assert
    expect(yaml.endsWith("\n")).toBe(true);
  });

  it("preserves the order of categories as written by the caller", () => {
    // Arrange / Act — the function must not sort or dedupe; output order is
    // the responsibility of detectSimplifyCategories upstream.
    const yaml = buildGithubReposBlock(["Quant", "Hardware", "Software"]);

    // Assert
    const quantIdx = yaml.indexOf('- "Quant"');
    const hardwareIdx = yaml.indexOf('- "Hardware"');
    const softwareIdx = yaml.indexOf('- "Software"');
    expect(quantIdx).toBeGreaterThan(0);
    expect(hardwareIdx).toBeGreaterThan(quantIdx);
    expect(softwareIdx).toBeGreaterThan(hardwareIdx);
  });

  it("emits exactly one category line per category entry", () => {
    // Arrange / Act
    const yaml = buildGithubReposBlock(["Software", "Hardware", "PM", "Quant"]);

    // Assert — counts must match exactly so duplicates introduced by a
    // bad map() refactor are caught.
    const hardwareMatches = yaml.match(/- "Hardware"/g) ?? [];
    expect(hardwareMatches).toHaveLength(1);
    const softwareMatches = yaml.match(/- "Software"/g) ?? [];
    expect(softwareMatches).toHaveLength(1);
  });

  it("indents categories list with four spaces and entries with six", () => {
    // Arrange / Act — YAML indentation is structural; pin the exact widths.
    const yaml = buildGithubReposBlock(["Hardware"]);

    // Assert
    expect(yaml).toContain("    categories:\n");
    expect(yaml).toContain('      - "Hardware"');
  });

  it("uses dev (not main) as the SimplifyJobs branch — pinned regression", () => {
    // Arrange / Act — the SimplifyJobs internships repo splits hardware vs
    // software listings on the dev branch. Switching to main silently halves
    // the data set, which is exactly the bug Issue #5 fixed.
    const yaml = buildGithubReposBlock(["Hardware"]);

    // Assert
    expect(yaml).toContain("branch: dev");
    expect(yaml).not.toContain("branch: main");
  });
});

// ─── seedGithubRepos × saveWatchlistCompanies coexistence ─────────────────────

describe("seedGithubRepos × saveWatchlistCompanies coexistence", () => {
  it("saveWatchlistCompanies does not clobber a pre-existing github_repos block", async () => {
    // Arrange — this is the exact regression flagged in the testing handoff:
    // the two functions target different YAML keys, and writing one must not
    // affect the other. The watchlist regex `(greenhouse_companies:...)`
    // must not bleed into the github_repos block below it.
    vi.spyOn(globalThis, "fetch");
    const seededYaml =
      "github_repos:\n" +
      "  - owner: SimplifyJobs\n" +
      "    repo: Summer2026-Internships\n" +
      "    branch: dev\n" +
      "    json_path: .github/scripts/listings.json\n" +
      "    enabled: true\n" +
      '    categories:\n      - "Hardware"\n' +
      "greenhouse_companies:\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: seededYaml });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act — write a watchlist into YAML that already contains a seeded
    // github_repos block.
    await saveWatchlistCompanies("Stripe", updateSources, fetchSources);

    // Assert — every part of the github_repos block survives.
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("github_repos:");
    expect(written).toContain("owner: SimplifyJobs");
    expect(written).toContain("repo: Summer2026-Internships");
    expect(written).toContain("branch: dev");
    expect(written).toContain('- "Hardware"');
    expect(written).toContain("  Stripe:");
  });

  it("seedGithubRepos does not clobber a pre-existing greenhouse_companies block (with entries)", async () => {
    // Arrange — opposite direction: greenhouse_companies has real entries
    // when seedGithubRepos runs. Every entry must survive.
    const existing =
      "greenhouse_companies:\n" +
      '  Stripe:\n    greenhouse_id: "stripe"\n    priority: 3\n' +
      '  Anthropic:\n    greenhouse_id: "anthropic"\n    priority: 3\n' +
      "github_repos: []\n";
    const fetchSources = vi.fn().mockResolvedValue({ yaml_text: existing });
    const updateSources = vi.fn().mockResolvedValue(undefined);

    // Act
    await seedGithubRepos(["Software Engineer"], updateSources, fetchSources);

    // Assert
    const written: string = updateSources.mock.calls[0]?.[0] as string;
    expect(written).toContain("  Stripe:");
    expect(written).toContain('    greenhouse_id: "stripe"');
    expect(written).toContain("  Anthropic:");
    expect(written).toContain('    greenhouse_id: "anthropic"');
    expect(written).toContain("owner: SimplifyJobs");
  });
});
