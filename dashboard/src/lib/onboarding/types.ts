/**
 * @packageDocumentation
 *
 * Shared types for the onboarding wizard.
 *
 * @remarks
 * Each step component owns a single draft slice; the parent
 * {@link ../../pages/OnboardingPage.OnboardingPage} composes the slices into
 * a final config payload at finish time. Keeping the slices in one module
 * lets the helpers in {@link ./yaml-builders} and {@link ./watchlist} stay
 * import-agnostic of the React components that render them.
 */

/** Draft state for step 1: basic profile info. */
export interface ProfileDraft {
  fullName: string;
  email: string;
  phone: string;
  city: string;
  stateOrRegion: string;
  countryCode: string;
  linkedinUrl: string;
  githubUrl: string;
  portfolioUrl: string;
  summary: string;
}

/** Draft state for step 2: target roles and preferences. */
export interface RolesDraft {
  targetRoles: string;
  strongestAreas: string;
  experienceHighlights: string;
  searchTerms: string;
}

/**
 * One row in the candidate's education history.
 *
 * @remarks
 * Captured by the new `StepEducation` wizard step (added 2026-05-25 because
 * the apply finisher was leaving Greenhouse education questions blank — no
 * upstream YAML had any entries). Maps 1:1 to the YAML shape consumed by
 * `CandidateEducationEntryPayload` on the backend, with two wizard-only
 * additions:
 *
 * - `minors` is captured as a free-form string list for the wizard UI; it
 *   serializes verbatim under each entry so existing tooling can read it.
 * - `currently_enrolled` is the user-facing checkbox; `is_current` on the
 *   backend payload is derived from it (still-enrolled rows often lack a
 *   final `end_date`, so we keep both signals).
 */
export interface EducationEntry {
  /** Stable client-generated identifier (e.g. `edu-1`). */
  id: string;
  school: string;
  degree: string;
  major: string;
  minors: string[];
  /** GPA as a free-form string so international scales (e.g. `10.0`) round-trip. */
  gpa: string;
  /** `YYYY-MM`, blank when unknown. */
  startDate: string;
  /** `YYYY-MM` (expected graduation for currently enrolled rows). */
  endDate: string;
  currentlyEnrolled: boolean;
}

/**
 * Tri-state relocation answer the apply finisher needs to surface for
 * "Are you willing to relocate?" prompts.
 *
 * @remarks
 * Replaces the prior boolean field; legacy YAML loaded via
 * `LocationPrefs` in `src/config/schema.py` is coerced (`false` → `"no"`,
 * `true` → `"yes"`) so existing candidate profiles keep loading.
 */
export type WillingToRelocate = "yes" | "no" | "open_to_discussion";

/** Draft state for step 4: hard filters. */
export interface FiltersDraft {
  minSalary: string;
  maxSalary: string;
  requireRemote: boolean;
  jobTypes: string[];
  excludeTitlePatterns: string;
  excludeCompanies: string;
}

/**
 * Draft state for step 5: AI provider.
 *
 * @remarks
 * The OSS launch ships with OpenAI BYOK as the only supported provider, so
 * this slice is just the API key the user typed. Mode/providerType/Codex
 * fields were removed when those code paths were stripped from the wizard.
 */
export interface ProviderDraft {
  /** OpenAI API key the user pasted into the wizard. May be empty. */
  apiKey: string;
  /** Optional Adzuna application ID for jobs-board coverage. */
  adzunaAppId: string;
  /** Optional Adzuna application key. */
  adzunaAppKey: string;
  /** Inline validation error for the Adzuna section, set during finish flow. */
  adzunaError?: string;
}

/** Draft state for step 6: company watchlist. */
export interface WatchlistDraft {
  companies: string;
}

/** EEO demographic defaults used by the apply finisher. */
export interface EeoDefaults {
  gender: string;
  race_ethnicity: string;
  veteran_status: string;
  disability_status: string;
}

/** Salary and hourly-rate expectations. */
export interface CompensationPrefs {
  expected_salary_min_usd: number | null;
  expected_salary_max_usd: number | null;
  expected_hourly_rate_usd: number | null;
}

/** Earliest-start and notice-period preferences. */
export interface AvailabilityPrefs {
  /** ISO date string `YYYY-MM-DD`, or `"flexible"`. */
  earliest_start_date: string;
  notice_period_weeks: number | null;
}

/** Geographic relocation and remote-work preferences. */
export interface LocationPrefs {
  willing_to_relocate: WillingToRelocate;
  preferred_cities: string[];
  willing_remote: boolean;
  willing_hybrid: boolean;
}

/** Application-level defaults supplied to the auto-apply finisher. */
export interface ApplicationDefaults {
  how_did_you_hear: string;
  /**
   * Confidence threshold (0.0–1.0) above which tier-2 answers are auto-submitted.
   * `1.0` means only fully-certain answers are submitted automatically.
   */
  tier2_confidence_threshold: number;
}

/** One entry in the candidate's languages list. */
export interface LanguageEntry {
  language: string;
  proficiency: "basic" | "conversational" | "fluent" | "native";
}

/** Draft state for step 7: apply preferences. */
export interface ApplyPrefsDraft {
  pronouns: string;
  eeo_defaults: EeoDefaults;
  /** `'unknown'` forces the user to make an explicit choice before finishing. */
  sponsorship_required_now_or_future: "yes" | "no" | "unknown";
  /** `'unknown'` forces the user to make an explicit choice before finishing. */
  work_authorized_us: "yes" | "no" | "unknown";
  compensation: CompensationPrefs;
  availability: AvailabilityPrefs;
  location_preferences: LocationPrefs;
  application_defaults: ApplicationDefaults;
  languages: LanguageEntry[];
}

/**
 * Outcome of probing a guessed Greenhouse board slug.
 *
 * @remarks
 * The previous boolean-only contract conflated two very different failure
 * modes — a real 404 (the slug is wrong) and a network-layer failure (we
 * could not reach Greenhouse at all). Surfacing them separately lets the
 * UI tell the user why their companies are unverified, and lets future
 * code retry the network case without prompting them to fix anything.
 */
export type GreenhouseSlugStatus =
  | "verified"
  | "not_found"
  | "network_error"
  /** Confirmed absent from Greenhouse — the company uses a different ATS. */
  | "not_on_greenhouse";

/**
 * Outcome of {@link ./watchlist.saveWatchlistCompanies}.
 *
 * @remarks
 * All three lists contain the user-facing company display names (not slugs).
 * Each represents a distinct failure mode with different UI copy:
 * `unverified` is the user's problem to fix (typo, slug mismatch);
 * `networkFailures` is our problem and may resolve on retry;
 * `notOnGreenhouse` means the company is confirmed to use a different ATS.
 */
export interface WatchlistSaveResult {
  /** Companies whose guessed slug returned a non-2xx response from Greenhouse. */
  readonly unverified: readonly string[];

  /**
   * Companies whose validation request never reached Greenhouse — the
   * entry was still written to disk, but the user should re-check the slug
   * once connectivity is restored.
   */
  readonly networkFailures: readonly string[];

  /**
   * Companies confirmed absent from Greenhouse (they use a different ATS).
   * No YAML entry is written for these companies.
   */
  readonly notOnGreenhouse: readonly string[];
}
