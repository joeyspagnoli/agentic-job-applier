/**
 * @packageDocumentation
 *
 * Pure helper that turns the wizard's per-step drafts into the structured
 * profile payload accepted by `updateProfileStructured`.
 *
 * @remarks
 * Kept out of the page shell so the JSX file stays focused on rendering.
 * The output shape mirrors the inline payload API contract — this helper
 * is just a re-key + line-split adapter.
 */

import type {
  ApplyPrefsDraft,
  EducationEntry,
  FiltersDraft,
  ProfileDraft,
  RolesDraft,
} from "./types";
import { splitLines } from "./yaml-builders";

/**
 * Argument bundle for {@link buildStructuredProfilePayload}.
 */
export interface BuildStructuredProfilePayloadArgs {
  readonly profile: ProfileDraft;
  readonly roles: RolesDraft;
  readonly filters: FiltersDraft;
  readonly applyPrefs: ApplyPrefsDraft;
  readonly education: readonly EducationEntry[];
}

/**
 * Shape of one education row inside the structured profile payload.
 *
 * @remarks
 * Mirrors `CandidateEducationEntryPayload` on the backend while exposing
 * the two wizard-specific extras (`minors`, derived `is_current` from the
 * checkbox). `start_year` / `end_year` etc. are split from the `YYYY-MM`
 * draft strings so the backend's structured payload stays unchanged.
 */
interface StructuredEducationEntry {
  readonly id: string;
  readonly school: string;
  readonly degree_level: string;
  readonly degree_name: string;
  readonly field_of_study: string;
  readonly start_month: string;
  readonly start_year: string;
  readonly end_month: string;
  readonly end_year: string;
  readonly is_current: boolean;
  readonly gpa: string;
  readonly location: string;
  readonly highlights: readonly string[];
  readonly minors: readonly string[];
}

/**
 * Split a `YYYY-MM` (or `YYYY/MM`, `YYYY MM`) draft string into discrete
 * year and month fields for the structured payload.
 *
 * @param raw - User-typed value from a wizard date input. Empty string is
 *   tolerated and produces two empty outputs.
 * @returns Tuple of `[year, month]` strings, each blank when missing.
 */
function _splitYearMonth(raw: string): readonly [string, string] {
  const trimmed = raw.trim();
  if (trimmed === "") return ["", ""];
  const parts = trimmed.split(/[-/ ]+/).map((piece) => piece.trim());
  const year = parts[0] ?? "";
  const month = parts[1] ?? "";
  return [year, month];
}

/**
 * Convert one wizard `EducationEntry` into the backend's structured shape.
 *
 * @param entry - Draft entry the user typed in the wizard.
 * @returns Structured payload row ready to embed in the profile payload.
 */
function _serializeEducationEntry(entry: EducationEntry): StructuredEducationEntry {
  const [startYear, startMonth] = _splitYearMonth(entry.startDate);
  const [endYear, endMonth] = _splitYearMonth(entry.endDate);
  return {
    id: entry.id,
    school: entry.school,
    degree_level: "",
    degree_name: entry.degree,
    field_of_study: entry.major,
    start_month: startMonth,
    start_year: startYear,
    end_month: endMonth,
    end_year: endYear,
    is_current: entry.currentlyEnrolled,
    gpa: entry.gpa,
    location: "",
    highlights: [],
    minors: entry.minors,
  };
}

/**
 * Convert wizard drafts into the structured profile payload.
 *
 * @param args - Profile, roles, filter, and apply-prefs drafts captured by the wizard.
 * @returns The payload shape consumed by `updateProfileStructured`.
 */
export function buildStructuredProfilePayload({
  profile,
  roles,
  filters,
  applyPrefs,
  education,
}: BuildStructuredProfilePayloadArgs): {
  profile: {
    summary: string;
    contact: {
      full_name: string;
      email: string;
      phone: string;
      city: string;
      state_or_region: string;
      country_code: string;
      country_label: string;
      linkedin_url: string;
      github_url: string;
      portfolio_url: string;
    };
    work_authorization: {
      citizenship_country_code: string;
      citizenship_country_label: string;
      authorized_to_work_us: "yes" | "no" | "unknown";
      requires_sponsorship_now_or_future: "yes" | "no" | "unknown";
    };
    education_summary: string;
    education_entries: readonly StructuredEducationEntry[];
    target_roles: string[];
    strongest_areas: string[];
    experience_highlights: string[];
    hard_filters: string[];
    preferences: readonly never[];
  };
  search_defaults: { job_board_search_terms: string[] };
  apply_prefs: ApplyPrefsDraft;
  prompt_context: null;
} {
  return {
    profile: {
      summary: profile.summary,
      contact: {
        full_name: profile.fullName,
        email: profile.email,
        phone: profile.phone,
        city: profile.city,
        state_or_region: profile.stateOrRegion,
        country_code: profile.countryCode,
        country_label: "",
        linkedin_url: profile.linkedinUrl,
        github_url: profile.githubUrl,
        portfolio_url: profile.portfolioUrl,
      },
      work_authorization: {
        citizenship_country_code: profile.countryCode,
        citizenship_country_label: "",
        authorized_to_work_us: applyPrefs.work_authorized_us,
        requires_sponsorship_now_or_future: applyPrefs.sponsorship_required_now_or_future,
      },
      education_summary: "",
      education_entries: education.map(_serializeEducationEntry),
      target_roles: splitLines(roles.targetRoles),
      strongest_areas: splitLines(roles.strongestAreas),
      experience_highlights: splitLines(roles.experienceHighlights),
      hard_filters: splitLines(filters.excludeTitlePatterns),
      preferences: [],
    },
    search_defaults: {
      job_board_search_terms: splitLines(roles.searchTerms),
    },
    apply_prefs: applyPrefs,
    prompt_context: null,
  };
}
