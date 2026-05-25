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
  ApplyPrefsDraft,
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
 * @returns Fresh provider draft with an empty OpenAI API key field.
 */
export function defaultProviderDraft(): ProviderDraft {
  return { apiKey: "", adzunaAppId: "", adzunaAppKey: "" };
}

/**
 * Build the default empty watchlist draft.
 *
 * @returns Fresh watchlist draft.
 */
export function defaultWatchlistDraft(): WatchlistDraft {
  return { companies: "" };
}

/**
 * Build the default apply-preferences draft.
 *
 * @returns Fresh apply-prefs draft with safe defaults.
 */
export function defaultApplyPrefsDraft(): ApplyPrefsDraft {
  return {
    pronouns: "",
    eeo_defaults: {
      gender: "prefer_not_to_say",
      race_ethnicity: "prefer_not_to_say",
      veteran_status: "prefer_not_to_say",
      disability_status: "prefer_not_to_say",
    },
    // Intentionally left at 'unknown' so the user is forced to answer.
    sponsorship_required_now_or_future: "unknown",
    work_authorized_us: "unknown",
    compensation: {
      expected_salary_min_usd: null,
      expected_salary_max_usd: null,
      expected_hourly_rate_usd: null,
    },
    availability: {
      earliest_start_date: "flexible",
      notice_period_weeks: null,
    },
    location_preferences: {
      willing_to_relocate: false,
      preferred_cities: [],
      willing_remote: true,
      willing_hybrid: true,
    },
    application_defaults: {
      how_did_you_hear: "",
      tier2_confidence_threshold: 1.0,
    },
    languages: [],
  };
}

/** Empty result returned when there are no companies to save. */
export const EMPTY_WATCHLIST_RESULT: WatchlistSaveResult = {
  unverified: [],
  networkFailures: [],
  notOnGreenhouse: [],
};
