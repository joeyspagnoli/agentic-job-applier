/**
 * @packageDocumentation
 *
 * Pure data transforms used by the settings page tabs. None of these helpers
 * touch React state; they only reshape data between backend DTOs and
 * UI-friendly drafts.
 */

import type {
  ApiKeyNameDto,
  CandidateEducationEntryDto,
  ResumeContentDto,
  ServiceTierDto,
  SettingsProfileDto,
  SettingsResumeDto,
} from "@/lib/api/types";
import { SERVICE_TIER_REQUIREMENTS } from "./constants";
import type { FiltersGuidedDraft } from "./types";

/** Mutable working copy of a settings profile DTO. */
export interface ProfileDraft {
  /** Mutable candidate profile structure. */
  profile: SettingsProfileDto["profile"];
  /** Mutable search-defaults structure. */
  search_defaults: SettingsProfileDto["search_defaults"];
  /** Optional override prompt context. */
  prompt_context: string | null;
}

/**
 * Convert list items to a newline-separated textarea value.
 *
 * @param items - List of values to flatten.
 * @returns Newline-separated text.
 */
export function listToLines(items: readonly string[]): string {
  return items.join("\n");
}

/**
 * Convert textarea content into normalized list values.
 *
 * @param value - Raw textarea value.
 * @returns Trimmed list with empty lines removed.
 */
export function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Parse a raw filters.yaml data object into a guided draft.
 *
 * @param data - Parsed YAML object from backend.
 * @returns Structured draft ready for the guided form.
 */
export function parseFiltersGuidedDraft(data: Record<string, unknown>): FiltersGuidedDraft {
  const hard = (data["hard_filters"] as Record<string, unknown> | undefined) ?? {};
  const soft = (data["soft_filters"] as Record<string, unknown> | undefined) ?? {};

  function getStringList(obj: Record<string, unknown>, key: string): string {
    const val = obj[key];
    return Array.isArray(val) ? listToLines(val as string[]) : "";
  }

  function getNumber(obj: Record<string, unknown>, key: string): string {
    const val = obj[key];
    return val !== undefined && val !== null ? String(val) : "0";
  }

  const excludeJobTypes = hard["exclude_job_types"];

  return {
    hard_exclude_job_types: Array.isArray(excludeJobTypes) ? (excludeJobTypes as string[]) : [],
    hard_exclude_title_patterns: getStringList(hard, "exclude_title_patterns"),
    hard_require_title_patterns: getStringList(hard, "require_title_patterns"),
    hard_exclude_locations: getStringList(hard, "exclude_locations"),
    hard_require_remote: hard["require_remote"] === true,
    hard_exclude_companies: getStringList(hard, "exclude_companies"),
    hard_max_days_old: getNumber(hard, "max_days_old"),
    hard_min_salary_usd: getNumber(hard, "min_salary_usd"),
    hard_max_salary_usd: getNumber(hard, "max_salary_usd"),
    soft_negative_keywords: getStringList(soft, "negative_keywords"),
    soft_positive_keywords: getStringList(soft, "positive_keywords"),
    soft_max_experience_years: getNumber(soft, "max_experience_years"),
  };
}

/**
 * Serialize a filters guided draft back to YAML text.
 *
 * @param draft - Guided draft from the structured form.
 * @returns YAML string for persistence.
 */
export function serializeFiltersGuidedToYaml(draft: FiltersGuidedDraft): string {
  function yamlList(lines: string, indent: string): string {
    const items = linesToList(lines);
    if (items.length === 0) {
      return "[]";
    }
    return "\n" + items.map((item) => `${indent}  - ${JSON.stringify(item)}`).join("\n");
  }

  function yamlJobTypeList(types: readonly string[], indent: string): string {
    if (types.length === 0) {
      return "[]";
    }
    return "\n" + types.map((t) => `${indent}  - ${JSON.stringify(t)}`).join("\n");
  }

  const maxDaysOld = Number.parseInt(draft.hard_max_days_old, 10) || 0;
  const minSalary = Number.parseFloat(draft.hard_min_salary_usd) || 0;
  const maxSalary = Number.parseFloat(draft.hard_max_salary_usd) || 0;
  const maxExpYears = Number.parseInt(draft.soft_max_experience_years, 10) || 0;

  return [
    "hard_filters:",
    `  exclude_job_types: ${yamlJobTypeList(draft.hard_exclude_job_types, " ")}`,
    `  exclude_title_patterns: ${yamlList(draft.hard_exclude_title_patterns, " ")}`,
    `  require_title_patterns: ${yamlList(draft.hard_require_title_patterns, " ")}`,
    `  exclude_locations: ${yamlList(draft.hard_exclude_locations, " ")}`,
    `  require_remote: ${draft.hard_require_remote}`,
    `  exclude_companies: ${yamlList(draft.hard_exclude_companies, " ")}`,
    `  max_days_old: ${maxDaysOld}`,
    `  min_salary_usd: ${minSalary}`,
    `  max_salary_usd: ${maxSalary}`,
    "",
    "soft_filters:",
    `  negative_keywords: ${yamlList(draft.soft_negative_keywords, " ")}`,
    `  positive_keywords: ${yamlList(draft.soft_positive_keywords, " ")}`,
    `  max_experience_years: ${maxExpYears}`,
    "",
  ].join("\n");
}

/**
 * Deep-clone settings profile response into mutable draft payload.
 *
 * @param response - Settings profile DTO from backend.
 * @returns Mutable profile draft object.
 */
export function toProfileDraft(response: SettingsProfileDto): ProfileDraft {
  return {
    profile: {
      ...response.profile,
      contact: { ...response.profile.contact },
      work_authorization: { ...response.profile.work_authorization },
      education_entries: response.profile.education_entries.map((entry) => ({
        ...entry,
        highlights: [...entry.highlights],
      })),
      target_roles: [...response.profile.target_roles],
      strongest_areas: [...response.profile.strongest_areas],
      experience_highlights: [...response.profile.experience_highlights],
      hard_filters: [...response.profile.hard_filters],
      preferences: [...response.profile.preferences],
    },
    search_defaults: {
      job_board_search_terms: [...response.search_defaults.job_board_search_terms],
    },
    prompt_context: response.prompt_context,
  };
}

/**
 * Deep-clone resume settings response into mutable draft payload.
 *
 * @param response - Resume settings DTO from backend.
 * @returns Mutable resume draft object.
 */
export function toResumeDraft(response: SettingsResumeDto): ResumeContentDto {
  return JSON.parse(JSON.stringify(response.resume)) as ResumeContentDto;
}

/**
 * Build one predictable listing identifier with a numeric suffix.
 *
 * @param prefix - Prefix for generated ID.
 * @param existingIds - Existing IDs for collision detection.
 * @returns Newly generated identifier.
 */
export function nextGeneratedId(prefix: string, existingIds: readonly string[]): string {
  let suffix = existingIds.length + 1;
  let candidateId = `${prefix}_${suffix}`;
  while (existingIds.includes(candidateId)) {
    suffix += 1;
    candidateId = `${prefix}_${suffix}`;
  }
  return candidateId;
}

/**
 * Build one empty education entry row for guided profile editing.
 *
 * @param entryId - Stable identifier for the new education row.
 * @returns New education entry payload with safe defaults.
 */
export function buildDefaultEducationEntry(entryId: string): CandidateEducationEntryDto {
  return {
    id: entryId,
    school: "",
    degree_level: "",
    degree_name: "",
    field_of_study: "",
    start_month: "",
    start_year: "",
    end_month: "",
    end_year: "",
    is_current: false,
    gpa: "",
    location: "",
    highlights: [],
  };
}

/**
 * Extract one human-readable error message from unknown mutation/query errors.
 *
 * @param error - Unknown error object from React Query.
 * @returns A message safe to show in UI.
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unknown error";
}

/**
 * Build a deterministic configured-status map for all known API keys.
 *
 * @param keys - API key status rows from backend or fallback defaults.
 * @returns Map of key name to configured boolean.
 */
export function buildConfiguredKeyMap(
  keys: readonly { name: ApiKeyNameDto; configured: boolean }[],
): Record<ApiKeyNameDto, boolean> {
  const configuredMap: Record<ApiKeyNameDto, boolean> = {
    OPENAI_API_KEY: false,
    GOOGLE_API_KEY: false,
    ANTHROPIC_API_KEY: false,
    ADZUNA_APP_ID: false,
    ADZUNA_APP_KEY: false,
  };
  keys.forEach((key) => {
    configuredMap[key.name] = key.configured;
  });
  return configuredMap;
}

/**
 * Resolve missing API-key prerequisites for one service tier.
 *
 * @param tier - Candidate service tier.
 * @param configuredKeyMap - Current configured statuses by key name.
 * @returns Required keys that are still missing.
 */
export function getMissingKeysForTier(
  tier: ServiceTierDto,
  configuredKeyMap: Readonly<Record<ApiKeyNameDto, boolean>>,
): ApiKeyNameDto[] {
  const requiredKeys = SERVICE_TIER_REQUIREMENTS[tier];
  return requiredKeys.filter((keyName) => !configuredKeyMap[keyName]);
}

/**
 * Count normalized list values currently present in one multiline field.
 *
 * @param value - Raw textarea value.
 * @returns Number of non-empty lines.
 */
export function countListItems(value: string): number {
  return linesToList(value).length;
}
