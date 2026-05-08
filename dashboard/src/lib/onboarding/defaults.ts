/**
 * @packageDocumentation
 *
 * Factory functions returning fresh draft slices for each onboarding step.
 *
 * @remarks
 * Each factory returns a new object on every call so the wizard never
 * mutates a shared default — important for React state correctness.
 */

import type {
  FiltersDraft,
  ProfileDraft,
  ProviderDraft,
  RolesDraft,
  WatchlistDraft,
  WatchlistSaveResult,
} from "./types";

/**
 * Build the default empty profile draft.
 *
 * @returns Fresh profile draft with empty fields.
 */
export function defaultProfileDraft(): ProfileDraft {
  return {
    fullName: "",
    email: "",
    phone: "",
    city: "",
    stateOrRegion: "",
    countryCode: "US",
    linkedinUrl: "",
    githubUrl: "",
    portfolioUrl: "",
    summary: "",
  };
}

/**
 * Build the default empty roles draft.
 *
 * @returns Fresh roles draft.
 */
export function defaultRolesDraft(): RolesDraft {
  return {
    targetRoles: "",
    strongestAreas: "",
    experienceHighlights: "",
    searchTerms: "",
  };
}

/**
 * Build the default filters draft.
 *
 * @returns Fresh filters draft.
 */
export function defaultFiltersDraft(): FiltersDraft {
  return {
    minSalary: "",
    maxSalary: "",
    requireRemote: false,
    jobTypes: ["Full-time"],
    excludeTitlePatterns: "",
    excludeCompanies: "",
  };
}

/**
 * Build the default provider draft.
 *
 * @returns Fresh provider draft.
 */
export function defaultProviderDraft(): ProviderDraft {
  return {
    mode: "byok",
    providerType: "openai",
    apiKey: "",
    codexStatus: "idle",
    codexUrl: null,
    codexCode: null,
  };
}

/**
 * Build the default empty watchlist draft.
 *
 * @returns Fresh watchlist draft.
 */
export function defaultWatchlistDraft(): WatchlistDraft {
  return { companies: "" };
}

/** Empty result returned when there are no companies to save. */
export const EMPTY_WATCHLIST_RESULT: WatchlistSaveResult = {
  unverified: [],
  networkFailures: [],
  notOnGreenhouse: [],
};
