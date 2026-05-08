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

import type { FiltersDraft, ProfileDraft, RolesDraft } from "./types";
import { splitLines } from "./yaml-builders";

/**
 * Argument bundle for {@link buildStructuredProfilePayload}.
 */
export interface BuildStructuredProfilePayloadArgs {
  readonly profile: ProfileDraft;
  readonly roles: RolesDraft;
  readonly filters: FiltersDraft;
}

/**
 * Convert wizard drafts into the structured profile payload.
 *
 * @param args - Profile, roles, and filter drafts captured by the wizard.
 * @returns The payload shape consumed by `updateProfileStructured`.
 */
export function buildStructuredProfilePayload({
  profile,
  roles,
  filters,
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
      authorized_to_work_us: "unknown";
      requires_sponsorship_now_or_future: "unknown";
    };
    education_summary: string;
    education_entries: readonly never[];
    target_roles: string[];
    strongest_areas: string[];
    experience_highlights: string[];
    hard_filters: string[];
    preferences: readonly never[];
  };
  search_defaults: { job_board_search_terms: string[] };
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
        authorized_to_work_us: "unknown",
        requires_sponsorship_now_or_future: "unknown",
      },
      education_summary: "",
      education_entries: [],
      target_roles: splitLines(roles.targetRoles),
      strongest_areas: splitLines(roles.strongestAreas),
      experience_highlights: splitLines(roles.experienceHighlights),
      hard_filters: splitLines(filters.excludeTitlePatterns),
      preferences: [],
    },
    search_defaults: {
      job_board_search_terms: splitLines(roles.searchTerms),
    },
    prompt_context: null,
  };
}
