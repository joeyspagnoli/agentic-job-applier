/**
 * @packageDocumentation
 *
 * Behavioral tests for the optional Adzuna section of {@link finishOnboarding}.
 *
 * @remarks
 * The finish-onboarding flow has four mutually exclusive Adzuna paths:
 *
 * 1. Both Adzuna fields blank → no Adzuna calls at all.
 * 2. Only one Adzuna field filled → throws before any side-effect.
 * 3. Both filled and {@link validateAdzunaKeys} succeeds → upserts both keys
 *    and flips `adzuna.enabled` in `companies.yaml`.
 * 4. Both filled and validation fails → no key upsert and no YAML flip.
 *
 * Each test stubs `@/lib/api/client` and the watchlist helpers so the only
 * code under test is the orchestration logic in {@link finishOnboarding}.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { finishOnboarding, type FinishOnboardingArgs } from "@/lib/onboarding/finish-onboarding";
import type {
  FiltersDraft,
  ProfileDraft,
  ProviderDraft,
  RolesDraft,
  WatchlistDraft,
} from "@/lib/onboarding/types";

// Mock every API-client function the finish flow may call so no real network
// activity escapes the test process.
vi.mock("@/lib/api/client", () => ({
  updateProfileStructured: vi.fn().mockResolvedValue({}),
  updateFiltersYaml: vi.fn().mockResolvedValue({}),
  upsertApiKeySetting: vi.fn().mockResolvedValue({}),
  validateAdzunaKeys: vi.fn().mockResolvedValue(undefined),
}));

// `seedGithubRepos` and `saveWatchlistCompanies` perform additional source-YAML
// updates that aren't relevant to the Adzuna flow; stub them out so each test
// can assert exactly which `updateSources` calls are Adzuna's.
vi.mock("@/lib/onboarding/watchlist", () => ({
  seedGithubRepos: vi.fn().mockResolvedValue(undefined),
  seedKeylessBoards: vi.fn().mockResolvedValue(undefined),
  saveWatchlistCompanies: vi.fn().mockResolvedValue({
    unverified: [],
    networkFailures: [],
    notOnGreenhouse: [],
  }),
}));

import * as apiClient from "@/lib/api/client";

/** Build a baseline empty profile draft. */
function emptyProfile(): ProfileDraft {
  return {
    fullName: "",
    email: "",
    phone: "",
    city: "",
    stateOrRegion: "",
    countryCode: "",
    linkedinUrl: "",
    githubUrl: "",
    portfolioUrl: "",
    summary: "",
  };
}

/** Build a baseline empty roles draft. */
function emptyRoles(): RolesDraft {
  return {
    targetRoles: "",
    strongestAreas: "",
    experienceHighlights: "",
    searchTerms: "",
  };
}

/** Build a baseline empty filters draft. */
function emptyFilters(): FiltersDraft {
  return {
    minSalary: "",
    maxSalary: "",
    requireRemote: false,
    jobTypes: [],
    excludeTitlePatterns: "",
    excludeCompanies: "",
  };
}

/** Build a baseline empty provider draft (no OpenAI, no Adzuna). */
function emptyProvider(): ProviderDraft {
  return {
    apiKey: "",
    adzunaAppId: "",
    adzunaAppKey: "",
  };
}

/** Build a baseline empty watchlist draft. */
function emptyWatchlist(): WatchlistDraft {
  return { companies: "" };
}

/** Args bundle plus typed handles for the mocked source-YAML hooks. */
interface BuiltArgs {
  args: FinishOnboardingArgs;
  fetchSources: ReturnType<typeof vi.fn>;
  updateSources: ReturnType<typeof vi.fn>;
  refetchOnboardingStatus: ReturnType<typeof vi.fn>;
}

/** Build a complete args bundle for {@link finishOnboarding}. */
function buildArgs(overrides: { provider?: ProviderDraft } = {}): BuiltArgs {
  const fetchSources = vi
    .fn()
    .mockResolvedValue({ yaml_text: "greenhouse_companies: {}\n" });
  const updateSources = vi.fn().mockResolvedValue(undefined);
  const refetchOnboardingStatus = vi.fn().mockResolvedValue(undefined);
  const args: FinishOnboardingArgs = {
    profile: emptyProfile(),
    roles: emptyRoles(),
    filters: emptyFilters(),
    provider: overrides.provider ?? emptyProvider(),
    watchlist: emptyWatchlist(),
    fetchSources: fetchSources as unknown as FinishOnboardingArgs["fetchSources"],
    updateSources: updateSources as unknown as FinishOnboardingArgs["updateSources"],
    refetchOnboardingStatus: refetchOnboardingStatus as unknown as FinishOnboardingArgs["refetchOnboardingStatus"],
  };
  return { args, fetchSources, updateSources, refetchOnboardingStatus };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("finishOnboarding — Adzuna section", () => {
  it("does not call validate or upsert when both Adzuna fields are blank", async () => {
    // Arrange
    const { args } = buildArgs();

    // Act
    await finishOnboarding(args);

    // Assert
    expect(apiClient.validateAdzunaKeys).not.toHaveBeenCalled();
    expect(apiClient.upsertApiKeySetting).not.toHaveBeenCalled();
  });

  it("does not call validate or upsert when both fields are whitespace-only", async () => {
    // Arrange
    const { args } = buildArgs({
      provider: { apiKey: "", adzunaAppId: "   ", adzunaAppKey: "\t\n " },
    });

    // Act
    await finishOnboarding(args);

    // Assert
    expect(apiClient.validateAdzunaKeys).not.toHaveBeenCalled();
    expect(apiClient.upsertApiKeySetting).not.toHaveBeenCalled();
  });

  it("throws before any API call when only the Adzuna app_id is filled", async () => {
    // Arrange
    const { args } = buildArgs({
      provider: { apiKey: "", adzunaAppId: "id-only", adzunaAppKey: "" },
    });

    // Act / Assert
    await expect(finishOnboarding(args)).rejects.toThrow(
      "Provide both Adzuna fields",
    );
    expect(apiClient.validateAdzunaKeys).not.toHaveBeenCalled();
    expect(apiClient.upsertApiKeySetting).not.toHaveBeenCalled();
  });

  it("throws before any API call when only the Adzuna app_key is filled", async () => {
    // Arrange
    const { args } = buildArgs({
      provider: { apiKey: "", adzunaAppId: "", adzunaAppKey: "key-only" },
    });

    // Act / Assert
    await expect(finishOnboarding(args)).rejects.toThrow(
      "Provide both Adzuna fields",
    );
    expect(apiClient.validateAdzunaKeys).not.toHaveBeenCalled();
    expect(apiClient.upsertApiKeySetting).not.toHaveBeenCalled();
  });

  it("validates, upserts both keys, and flips adzuna.enabled when both fields are filled", async () => {
    // Arrange
    const { args, updateSources } = buildArgs({
      provider: {
        apiKey: "",
        adzunaAppId: "id-real",
        adzunaAppKey: "key-real",
      },
    });

    // Act
    await finishOnboarding(args);

    // Assert: validation runs first, then both upsert calls in canonical order.
    expect(apiClient.validateAdzunaKeys).toHaveBeenCalledWith("id-real", "key-real");
    expect(apiClient.upsertApiKeySetting).toHaveBeenCalledWith(
      "ADZUNA_APP_ID",
      "id-real",
    );
    expect(apiClient.upsertApiKeySetting).toHaveBeenCalledWith(
      "ADZUNA_APP_KEY",
      "key-real",
    );
    expect(apiClient.upsertApiKeySetting).toHaveBeenCalledTimes(2);
    // The first updateSources call carries the YAML with the flipped Adzuna toggle.
    const firstUpdateYaml = updateSources.mock.calls[0]?.[0] as string;
    expect(firstUpdateYaml).toContain("adzuna:");
    expect(firstUpdateYaml).toContain("enabled: true");
  });

  it("trims whitespace before sending Adzuna credentials downstream", async () => {
    // Arrange
    const { args } = buildArgs({
      provider: {
        apiKey: "",
        adzunaAppId: "  padded-id  ",
        adzunaAppKey: "\tpadded-key\n",
      },
    });

    // Act
    await finishOnboarding(args);

    // Assert
    expect(apiClient.validateAdzunaKeys).toHaveBeenCalledWith(
      "padded-id",
      "padded-key",
    );
    expect(apiClient.upsertApiKeySetting).toHaveBeenCalledWith(
      "ADZUNA_APP_ID",
      "padded-id",
    );
    expect(apiClient.upsertApiKeySetting).toHaveBeenCalledWith(
      "ADZUNA_APP_KEY",
      "padded-key",
    );
  });

  it("propagates validation failures and skips upsert + YAML flip", async () => {
    // Arrange
    const validationError = new Error("Adzuna validation failed (HTTP 401).");
    vi.mocked(apiClient.validateAdzunaKeys).mockRejectedValueOnce(validationError);

    const { args, updateSources } = buildArgs({
      provider: {
        apiKey: "",
        adzunaAppId: "id-bad",
        adzunaAppKey: "key-bad",
      },
    });

    // Act / Assert
    await expect(finishOnboarding(args)).rejects.toBe(validationError);
    expect(apiClient.upsertApiKeySetting).not.toHaveBeenCalled();
    expect(updateSources).not.toHaveBeenCalled();
  });

  it("calls validate exactly once before any upsert (order matters)", async () => {
    // Arrange
    const callOrder: string[] = [];
    vi.mocked(apiClient.validateAdzunaKeys).mockImplementationOnce(async () => {
      callOrder.push("validate");
    });
    vi.mocked(apiClient.upsertApiKeySetting).mockImplementation(async () => {
      callOrder.push("upsert");
      return {} as never;
    });

    const { args } = buildArgs({
      provider: {
        apiKey: "",
        adzunaAppId: "id",
        adzunaAppKey: "key",
      },
    });

    // Act
    await finishOnboarding(args);

    // Assert: validation lands strictly before either upsert.
    expect(callOrder[0]).toBe("validate");
    expect(callOrder.slice(1)).toEqual(["upsert", "upsert"]);
  });
});
