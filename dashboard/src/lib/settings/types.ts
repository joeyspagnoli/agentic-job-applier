/**
 * @packageDocumentation
 *
 * Shared type definitions for the settings page and its tab components.
 */

import type { ApiKeyNameDto } from "@/lib/api/types";

/** Top-level settings tab identifiers. */
export type TopLevelTab = "general" | "candidate" | "filters";

/** Candidate-profile sub-tab identifiers. */
export type CandidateTab = "guided" | "yaml" | "files";

/** Filters-and-sources sub-tab identifiers. */
export type FiltersTab = "guided" | "filters" | "sources";

/** Structured form state for the filters.yaml guided editor. */
export interface FiltersGuidedDraft {
  /** Job types to exclude outright (checkbox list). */
  readonly hard_exclude_job_types: readonly string[];
  /** Title patterns to reject — one regex per line. */
  readonly hard_exclude_title_patterns: string;
  /** Title patterns required to keep — one regex per line. */
  readonly hard_require_title_patterns: string;
  /** Location substrings to reject — one per line. */
  readonly hard_exclude_locations: string;
  /** When true only keep remote/hybrid jobs. */
  readonly hard_require_remote: boolean;
  /** Company names to never import — one per line. */
  readonly hard_exclude_companies: string;
  /** Reject jobs older than this many days (0 = disabled). */
  readonly hard_max_days_old: string;
  /** Minimum salary in USD (0 = disabled). */
  readonly hard_min_salary_usd: string;
  /** Maximum salary in USD (0 = disabled). */
  readonly hard_max_salary_usd: string;
  /** Description keywords that auto-FILTER — one per line. */
  readonly soft_negative_keywords: string;
  /** Description keywords that auto-QUALIFY — one per line. */
  readonly soft_positive_keywords: string;
  /** Auto-filter if description mentions more than this many years (0 = disabled). */
  readonly soft_max_experience_years: string;
}

/** UI configuration for an API key entry. */
export interface ApiKeyConfig {
  /** Backend identifier for the API key. */
  readonly name: ApiKeyNameDto;
  /** Material symbol icon name. */
  readonly icon: string;
  /** Human-readable description shown in the row. */
  readonly description: string;
}

/** Inline feedback message used by API-key sections. */
export interface FeedbackMessage {
  /** Visual variant for color treatment. */
  readonly type: "success" | "error";
  /** Display text. */
  readonly message: string;
}

/** Single option entry for `<select>` controls. */
export interface SelectOption {
  /** Option value submitted on change. */
  readonly value: string;
  /** Display label shown in the dropdown. */
  readonly label: string;
}
