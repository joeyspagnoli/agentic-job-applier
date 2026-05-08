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
}

/** Draft state for step 6: company watchlist. */
export interface WatchlistDraft {
  companies: string;
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
