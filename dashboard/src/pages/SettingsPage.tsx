/**
 * @packageDocumentation
 *
 * Tabbed settings page with guided and advanced editors for budget controls,
 * API keys, service tier, candidate profile, resume content, and YAML-managed
 * filters/sources files.
 */

import type { ChangeEvent, JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatUsd } from "@/lib/api/adapters";
import {
  deleteApiKeySetting,
  fetchApiKeysSettings,
  fetchBudget,
  fetchFiltersSettings,
  fetchProfileSettings,
  fetchResumeSettings,
  fetchServiceTierSetting,
  fetchSettingsFiles,
  fetchSourcesSettings,
  getProfileDownloadUrl,
  getResumeDownloadUrl,
  updateBudget,
  updateFiltersYaml,
  updateProfileStructured,
  updateProfileYaml,
  updateResumeStructured,
  updateResumeYaml,
  updateServiceTierSetting,
  updateSourcesYaml,
  uploadProfile,
  uploadResume,
  uploadResumeTex,
  upsertApiKeySetting,
} from "@/lib/api/client";
import type {
  ApiKeyNameDto,
  CandidateEducationEntryDto,
  ResumeContentDto,
  ResumeSkillListingDto,
  ServiceTierDto,
  SettingsProfileDto,
  SettingsResumeDto,
} from "@/lib/api/types";
import { buildPrioritizedCountryOptions } from "@/lib/constants/countries";
import {
  configureYamlSchemas,
  PROFILE_EDITOR_MODEL_URI,
  RESUME_EDITOR_MODEL_URI,
} from "@/lib/monaco/yaml-config";
import {
  COLOR_ERROR,
  COLOR_ERROR_CONTAINER,
  COLOR_ON_ERROR_CONTAINER,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_ON_WARNING_CONTAINER,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SUCCESS,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { AIProviderSettings } from "@/pages/settings/AIProviderSettings";

type TopLevelTab = "general" | "ai-provider" | "candidate" | "filters";
type CandidateTab = "guided" | "yaml" | "files";
type ResumeTab = "guided" | "yaml" | "tex" | "files";
type FiltersTab = "guided" | "filters" | "sources";

/** All job type values recognized by the filters hard-filter. */
const JOB_TYPES: readonly string[] = ["Full-time", "Part-time", "Contract", "Internship"];

/** Structured form state for the filters.yaml guided editor. */
interface FiltersGuidedDraft {
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

interface ApiKeyConfig {
  readonly name: ApiKeyNameDto;
  readonly icon: string;
  readonly description: string;
}

interface ServiceTierCard {
  readonly tier: ServiceTierDto;
  readonly icon: string;
  readonly title: string;
  readonly description: string;
  readonly features: readonly string[];
  readonly badge?: string;
}

interface FeedbackMessage {
  readonly type: "success" | "error";
  readonly message: string;
}

interface SelectOption {
  readonly value: string;
  readonly label: string;
}

const EDITOR_HEIGHT_PX = 420;
const TOP_LEVEL_TABS: readonly { id: TopLevelTab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "ai-provider", label: "AI Provider" },
  { id: "candidate", label: "Profile & Resume" },
  { id: "filters", label: "Filters & Sources" },
];
const API_KEYS: readonly ApiKeyConfig[] = [
  {
    name: "OPENAI_API_KEY",
    icon: "auto_awesome",
    description: "Required for gate review, resume tailoring, and full automation.",
  },
  {
    name: "GOOGLE_API_KEY",
    icon: "auto_awesome",
    description: "Optional provider key for alternative model routing.",
  },
  {
    name: "ANTHROPIC_API_KEY",
    icon: "auto_awesome",
    description: "Optional provider key for alternative model routing.",
  },
  {
    name: "APIFY_API_TOKEN",
    icon: "api",
    description: "Required for Workday and JobSpy-backed source coverage.",
  },
];
const SERVICE_TIER_REQUIREMENTS: Readonly<Record<ServiceTierDto, readonly ApiKeyNameDto[]>> = {
  base: [],
  latex: ["OPENAI_API_KEY"],
  full: ["OPENAI_API_KEY", "APIFY_API_TOKEN"],
};
const SERVICE_TIER_CARDS: readonly ServiceTierCard[] = [
  {
    tier: "base",
    icon: "search",
    title: "Base",
    description:
      "Find and filter jobs from configured sources. Gate review is attempted when a provider key exists.",
    features: [
      "Job discovery (Greenhouse, JobSpy, Workday)",
      "Gate filtering (apply/skip decisions)",
      "Works as pure job aggregator without AI keys",
    ],
  },
  {
    tier: "latex",
    icon: "description",
    title: "LaTeX",
    badge: "Recommended",
    description: "Find jobs + tailor resume + human review queue.",
    features: ["Everything in Base", "Resume tailoring (LaTeX/PDF)", "Human review queue"],
  },
  {
    tier: "full",
    icon: "rocket_launch",
    title: "Full",
    description: "Full automation including browser-based application workflows.",
    features: [
      "Everything in LaTeX",
      "Automated browser apply (Playwright + Chromium)",
      "End-to-end autonomous pipeline",
    ],
  },
];
const CONFIRM_SWITCH_MESSAGE =
  "You have unsaved settings changes. Switch tabs and discard unsaved edits?";
const MONTH_OPTIONS: readonly SelectOption[] = [
  { value: "", label: "Month" },
  { value: "01", label: "January" },
  { value: "02", label: "February" },
  { value: "03", label: "March" },
  { value: "04", label: "April" },
  { value: "05", label: "May" },
  { value: "06", label: "June" },
  { value: "07", label: "July" },
  { value: "08", label: "August" },
  { value: "09", label: "September" },
  { value: "10", label: "October" },
  { value: "11", label: "November" },
  { value: "12", label: "December" },
];
const DEGREE_LEVEL_OPTIONS: readonly SelectOption[] = [
  { value: "", label: "Select degree level" },
  { value: "high_school", label: "High School" },
  { value: "associate", label: "Associate" },
  { value: "bachelor", label: "Bachelor's" },
  { value: "master", label: "Master's" },
  { value: "mba", label: "MBA" },
  { value: "doctorate", label: "Doctorate" },
  { value: "certificate", label: "Certificate" },
  { value: "other", label: "Other" },
];
const YES_NO_UNKNOWN_OPTIONS: readonly SelectOption[] = [
  { value: "unknown", label: "Prefer not to say" },
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

/**
 * Convert list items to a newline-separated textarea value.
 *
 * @param items - List of values to flatten.
 * @returns Newline-separated text.
 */
function listToLines(items: readonly string[]): string {
  return items.join("\n");
}

/**
 * Convert textarea content into normalized list values.
 *
 * @param value - Raw textarea value.
 * @returns Trimmed list with empty lines removed.
 */
function linesToList(value: string): string[] {
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
function parseFiltersGuidedDraft(data: Record<string, unknown>): FiltersGuidedDraft {
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
    hard_exclude_job_types: Array.isArray(excludeJobTypes)
      ? (excludeJobTypes as string[])
      : [],
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
function serializeFiltersGuidedToYaml(draft: FiltersGuidedDraft): string {
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
function toProfileDraft(response: SettingsProfileDto): {
  profile: SettingsProfileDto["profile"];
  search_defaults: SettingsProfileDto["search_defaults"];
  prompt_context: string | null;
} {
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
function toResumeDraft(response: SettingsResumeDto): ResumeContentDto {
  return JSON.parse(JSON.stringify(response.resume)) as ResumeContentDto;
}

/**
 * Build one predictable listing identifier with a numeric suffix.
 *
 * @param prefix - Prefix for generated ID.
 * @param existingIds - Existing IDs for collision detection.
 * @returns Newly generated identifier.
 */
function nextGeneratedId(prefix: string, existingIds: readonly string[]): string {
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
function buildDefaultEducationEntry(entryId: string): CandidateEducationEntryDto {
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
function getErrorMessage(error: unknown): string {
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
function buildConfiguredKeyMap(
  keys: readonly { name: ApiKeyNameDto; configured: boolean }[],
): Record<ApiKeyNameDto, boolean> {
  const configuredMap: Record<ApiKeyNameDto, boolean> = {
    OPENAI_API_KEY: false,
    GOOGLE_API_KEY: false,
    ANTHROPIC_API_KEY: false,
    APIFY_API_TOKEN: false,
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
function getMissingKeysForTier(
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
function countListItems(value: string): number {
  return linesToList(value).length;
}

/**
 * Settings page component.
 *
 * @returns Full tabbed settings page with guided + advanced editors.
 */
export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const profileYamlInputRef = useRef<HTMLInputElement | null>(null);
  const resumeYamlInputRef = useRef<HTMLInputElement | null>(null);
  const resumeTexInputRef = useRef<HTMLInputElement | null>(null);

  const [activeTopLevelTab, setActiveTopLevelTab] = useState<TopLevelTab>("general");
  const [activeFiltersTab, setActiveFiltersTab] = useState<FiltersTab>("guided");
  const [candidateTab, setCandidateTab] = useState<CandidateTab>("guided");
  const [resumeTab, setResumeTab] = useState<ResumeTab>("guided");

  const [budgetInput, setBudgetInput] = useState("0.00");
  const [profileDraft, setProfileDraft] = useState<ReturnType<typeof toProfileDraft> | null>(null);
  const [resumeDraft, setResumeDraft] = useState<ResumeContentDto | null>(null);
  const [filtersGuidedDraft, setFiltersGuidedDraft] = useState<FiltersGuidedDraft | null>(null);
  const [profileYamlDraft, setProfileYamlDraft] = useState("");
  const [resumeYamlDraft, setResumeYamlDraft] = useState("");
  const [filtersYamlDraft, setFiltersYamlDraft] = useState("");
  const [sourcesYamlDraft, setSourcesYamlDraft] = useState("");

  const [isBudgetDirty, setIsBudgetDirty] = useState(false);
  const [isProfileDirty, setIsProfileDirty] = useState(false);
  const [isResumeDirty, setIsResumeDirty] = useState(false);
  const [isFiltersDirty, setIsFiltersDirty] = useState(false);
  const [isFiltersGuidedDirty, setIsFiltersGuidedDirty] = useState(false);
  const [isSourcesDirty, setIsSourcesDirty] = useState(false);
  const [isTierDirty, setIsTierDirty] = useState(false);

  const [selectedServiceTier, setSelectedServiceTier] = useState<ServiceTierDto>("base");
  const [editingApiKeyName, setEditingApiKeyName] = useState<ApiKeyNameDto | null>(null);
  const [editingApiKeyValue, setEditingApiKeyValue] = useState("");
  const [lastResumeMigrationSummary, setLastResumeMigrationSummary] = useState<string | null>(null);
  const [apiKeyFeedback, setApiKeyFeedback] = useState<FeedbackMessage | null>(null);
  const [tierFeedback, setTierFeedback] = useState<FeedbackMessage | null>(null);

  const budgetQuery = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const profileQuery = useQuery({
    queryKey: ["settings", "profile"],
    queryFn: fetchProfileSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const needsResume = selectedServiceTier === "latex" || selectedServiceTier === "full";

  const resumeQuery = useQuery({
    queryKey: ["settings", "resume"],
    queryFn: fetchResumeSettings,
    enabled: needsResume,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const filesQuery = useQuery({
    queryKey: ["settings", "files"],
    queryFn: fetchSettingsFiles,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const filtersQuery = useQuery({
    queryKey: ["settings", "filters"],
    queryFn: fetchFiltersSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const sourcesQuery = useQuery({
    queryKey: ["settings", "sources"],
    queryFn: fetchSourcesSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const apiKeysQuery = useQuery({
    queryKey: ["settings", "api-keys"],
    queryFn: fetchApiKeysSettings,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const tierQuery = useQuery({
    queryKey: ["settings", "service-tier"],
    queryFn: fetchServiceTierSetting,
    retry: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (budgetQuery.data !== undefined && !isBudgetDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBudgetInput(budgetQuery.data.monthly_budget_usd.toFixed(2));
    }
  }, [budgetQuery.data, isBudgetDirty]);

  useEffect(() => {
    if (profileQuery.data !== undefined && !isProfileDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProfileDraft(toProfileDraft(profileQuery.data));
      setProfileYamlDraft(profileQuery.data.yaml_text);
    }
  }, [profileQuery.data, isProfileDirty]);

  useEffect(() => {
    if (resumeQuery.data !== undefined && !isResumeDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResumeDraft(toResumeDraft(resumeQuery.data));
      setResumeYamlDraft(resumeQuery.data.yaml_text);
    }
  }, [resumeQuery.data, isResumeDirty]);

  useEffect(() => {
    if (filtersQuery.data !== undefined && !isFiltersDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFiltersYamlDraft(filtersQuery.data.yaml_text);
    }
    if (filtersQuery.data !== undefined && !isFiltersGuidedDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFiltersGuidedDraft(parseFiltersGuidedDraft(filtersQuery.data.data));
    }
  }, [filtersQuery.data, isFiltersDirty, isFiltersGuidedDirty]);

  useEffect(() => {
    if (sourcesQuery.data !== undefined && !isSourcesDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSourcesYamlDraft(sourcesQuery.data.yaml_text);
    }
  }, [sourcesQuery.data, isSourcesDirty]);

  useEffect(() => {
    if (tierQuery.data !== undefined && !isTierDirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedServiceTier(tierQuery.data.tier);
    }
  }, [tierQuery.data, isTierDirty]);

  useEffect(() => {
    if (apiKeyFeedback === null) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setApiKeyFeedback(null);
    }, 3000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [apiKeyFeedback]);

  useEffect(() => {
    if (tierFeedback === null) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setTierFeedback(null);
    }, 3000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [tierFeedback]);

  const budgetMutation = useMutation({
    mutationFn: updateBudget,
    onSuccess: async (response) => {
      queryClient.setQueryData(["budget"], response);
      setBudgetInput(response.monthly_budget_usd.toFixed(2));
      setIsBudgetDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const profileStructuredMutation = useMutation({
    mutationFn: updateProfileStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileYamlMutation = useMutation({
    mutationFn: updateProfileYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileUploadMutation = useMutation({
    mutationFn: uploadProfile,
    onSuccess: async () => {
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeStructuredMutation = useMutation({
    mutationFn: updateResumeStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setIsResumeDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeYamlMutation = useMutation({
    mutationFn: updateResumeYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setIsResumeDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeUploadMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: async () => {
      setIsResumeDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "resume"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeTexMutation = useMutation({
    mutationFn: uploadResumeTex,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setIsResumeDirty(false);
      setLastResumeMigrationSummary(
        `${response.migration.experience_listings} experience listings, ` +
          `${response.migration.project_listings} project listings, ` +
          `${response.migration.skill_rows} skills rows`,
      );
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const filtersYamlMutation = useMutation({
    mutationFn: updateFiltersYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "filters"], response);
      setFiltersYamlDraft(response.yaml_text);
      setFiltersGuidedDraft(parseFiltersGuidedDraft(response.data));
      setIsFiltersDirty(false);
      setIsFiltersGuidedDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "filters"] });
    },
  });

  const sourcesYamlMutation = useMutation({
    mutationFn: updateSourcesYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "sources"], response);
      setSourcesYamlDraft(response.yaml_text);
      setIsSourcesDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "sources"] });
    },
  });

  const apiKeyUpsertMutation = useMutation({
    mutationFn: (payload: { keyName: ApiKeyNameDto; keyValue: string }) =>
      upsertApiKeySetting(payload.keyName, payload.keyValue),
    onSuccess: async (response, payload) => {
      queryClient.setQueryData(["settings", "api-keys"], response);
      setEditingApiKeyName(null);
      setEditingApiKeyValue("");
      setApiKeyFeedback({
        type: "success",
        message: `${payload.keyName} saved.`,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "api-keys"] });
    },
    onError: (error, payload) => {
      setApiKeyFeedback({
        type: "error",
        message: `Failed to save ${payload.keyName}: ${getErrorMessage(error)}`,
      });
    },
  });

  const apiKeyDeleteMutation = useMutation({
    mutationFn: (keyName: ApiKeyNameDto) => deleteApiKeySetting(keyName),
    onSuccess: async (response, keyName) => {
      queryClient.setQueryData(["settings", "api-keys"], response);
      if (editingApiKeyName === keyName) {
        setEditingApiKeyName(null);
        setEditingApiKeyValue("");
      }
      setApiKeyFeedback({
        type: "success",
        message: `${keyName} removed.`,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "api-keys"] });
    },
    onError: (error, keyName) => {
      setApiKeyFeedback({
        type: "error",
        message: `Failed to remove ${keyName}: ${getErrorMessage(error)}`,
      });
    },
  });

  const tierMutation = useMutation({
    mutationFn: updateServiceTierSetting,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "service-tier"], response);
      setSelectedServiceTier(response.tier);
      setIsTierDirty(false);
      setTierFeedback({
        type: "success",
        message: `Service tier saved as ${response.tier.toUpperCase()}.`,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "service-tier"] });
    },
    onError: (error) => {
      setTierFeedback({
        type: "error",
        message: `Failed to save service tier: ${getErrorMessage(error)}`,
      });
    },
  });

  const profileMetadata = profileQuery.data?.metadata ?? filesQuery.data?.profile;
  const resumeMetadata = resumeQuery.data?.metadata ?? filesQuery.data?.resume;
  const budgetUsedPct = Math.max(
    0,
    Math.min(100, Math.round(budgetQuery.data?.utilization_pct ?? 0)),
  );
  const budgetProgressColor = budgetUsedPct >= 100 ? COLOR_ERROR : COLOR_PRIMARY;

  const normalizedApiKeys = useMemo(
    () =>
      API_KEYS.map((apiKey) => ({
        name: apiKey.name,
        configured:
          apiKeysQuery.data?.keys.find((responseKey) => responseKey.name === apiKey.name)
            ?.configured ?? false,
      })),
    [apiKeysQuery.data],
  );
  const configuredApiKeyMap = useMemo(
    () => buildConfiguredKeyMap(normalizedApiKeys),
    [normalizedApiKeys],
  );
  const countryOptions = useMemo(() => buildPrioritizedCountryOptions(), []);
  const countryLabelByCode = useMemo(
    () =>
      new Map<string, string>(
        countryOptions.map((countryOption) => [countryOption.code, countryOption.label]),
      ),
    [countryOptions],
  );
  const selectedTierMissingKeys = useMemo(
    () => getMissingKeysForTier(selectedServiceTier, configuredApiKeyMap),
    [configuredApiKeyMap, selectedServiceTier],
  );

  const canOpenResumeEditor = selectedServiceTier === "latex" || selectedServiceTier === "full";

  const resumeCountsText = useMemo(() => {
    if (resumeQuery.data === undefined) {
      return "Loading resume counts...";
    }
    return [
      `${resumeQuery.data.counts.education_entries} education entries`,
      `${resumeQuery.data.counts.experience_listings} experience listings`,
      `${resumeQuery.data.counts.project_listings} project listings`,
      `${resumeQuery.data.counts.skill_rows} skills rows`,
    ].join(" • ");
  }, [resumeQuery.data]);

  const hasUnsavedChanges =
    isBudgetDirty ||
    isProfileDirty ||
    isResumeDirty ||
    isFiltersDirty ||
    isFiltersGuidedDirty ||
    isSourcesDirty ||
    isTierDirty ||
    editingApiKeyName !== null;

  const hasAnyError =
    budgetQuery.isError ||
    profileQuery.isError ||
    (needsResume && resumeQuery.isError) ||
    filesQuery.isError ||
    filtersQuery.isError ||
    sourcesQuery.isError ||
    budgetMutation.isError ||
    profileStructuredMutation.isError ||
    profileYamlMutation.isError ||
    profileUploadMutation.isError ||
    (needsResume && resumeStructuredMutation.isError) ||
    (needsResume && resumeYamlMutation.isError) ||
    (needsResume && resumeUploadMutation.isError) ||
    (needsResume && resumeTexMutation.isError) ||
    filtersYamlMutation.isError ||
    sourcesYamlMutation.isError;

  function updateProfileDraft(
    nextDraft:
      | ReturnType<typeof toProfileDraft>
      | ((currentDraft: ReturnType<typeof toProfileDraft>) => ReturnType<typeof toProfileDraft>),
  ): void {
    setProfileDraft((currentDraft) => {
      if (currentDraft === null) {
        return currentDraft;
      }
      if (typeof nextDraft === "function") {
        return nextDraft(currentDraft);
      }
      return nextDraft;
    });
    setIsProfileDirty(true);
  }

  function updateResumeDraft(nextDraft: ResumeContentDto): void {
    setResumeDraft(nextDraft);
    setIsResumeDirty(true);
  }

  function updateProfileYamlDraft(nextYaml: string): void {
    setProfileYamlDraft(nextYaml);
    setIsProfileDirty(true);
  }

  function updateResumeYamlDraft(nextYaml: string): void {
    setResumeYamlDraft(nextYaml);
    setIsResumeDirty(true);
  }

  function handleTopLevelTabChange(nextTab: TopLevelTab): void {
    if (nextTab === activeTopLevelTab) {
      return;
    }
    if (hasUnsavedChanges && !window.confirm(CONFIRM_SWITCH_MESSAGE)) {
      return;
    }
    setActiveTopLevelTab(nextTab);
  }

  function handleFiltersTabChange(nextTab: FiltersTab): void {
    if (nextTab === activeFiltersTab) {
      return;
    }
    const hasCurrentTabUnsavedChanges =
      (activeFiltersTab === "guided" && isFiltersGuidedDirty) ||
      (activeFiltersTab === "filters" && isFiltersDirty) ||
      (activeFiltersTab === "sources" && isSourcesDirty);
    if (hasCurrentTabUnsavedChanges && !window.confirm(CONFIRM_SWITCH_MESSAGE)) {
      return;
    }
    setActiveFiltersTab(nextTab);
  }

  function handleFiltersGuidedSave(): void {
    if (filtersGuidedDraft === null) {
      return;
    }
    const yamlText = serializeFiltersGuidedToYaml(filtersGuidedDraft);
    filtersYamlMutation.mutate(yamlText);
  }

  function updateFiltersGuidedDraft(nextDraft: FiltersGuidedDraft): void {
    setFiltersGuidedDraft(nextDraft);
    setIsFiltersGuidedDirty(true);
  }

  function handleBudgetSave(): void {
    const parsedBudget = Number.parseFloat(budgetInput);
    if (!Number.isFinite(parsedBudget) || parsedBudget < 0) {
      return;
    }
    budgetMutation.mutate(parsedBudget);
  }

  function handleProfileListUpdate(
    fieldName: keyof SettingsProfileDto["profile"],
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    if (
      fieldName === "target_roles" ||
      fieldName === "strongest_areas" ||
      fieldName === "experience_highlights" ||
      fieldName === "hard_filters" ||
      fieldName === "preferences"
    ) {
      updateProfileDraft({
        ...profileDraft,
        profile: {
          ...profileDraft.profile,
          [fieldName]: linesToList(value),
        },
      });
    }
  }

  function handleProfileScalarUpdate(
    fieldName: "summary" | "education_summary",
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        [fieldName]: value,
      },
    });
  }

  function handleProfileContactFieldUpdate(
    fieldName: keyof SettingsProfileDto["profile"]["contact"],
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        contact: {
          ...profileDraft.profile.contact,
          [fieldName]: value,
        },
      },
    });
  }

  function handleProfileContactCountryUpdate(countryCode: string): void {
    updateProfileDraft((currentDraft) => {
      const selectedCountryLabel = countryLabelByCode.get(countryCode) ?? "";
      return {
        ...currentDraft,
        profile: {
          ...currentDraft.profile,
          contact: {
            ...currentDraft.profile.contact,
            country_code: countryCode,
            country_label: selectedCountryLabel,
          },
        },
      };
    });
  }

  function handleProfileWorkAuthorizationFieldUpdate(
    fieldName: keyof SettingsProfileDto["profile"]["work_authorization"],
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        work_authorization: {
          ...profileDraft.profile.work_authorization,
          [fieldName]: value,
        },
      },
    });
  }

  function handleProfileCitizenshipCountryUpdate(countryCode: string): void {
    updateProfileDraft((currentDraft) => {
      const selectedCountryLabel = countryLabelByCode.get(countryCode) ?? "";
      return {
        ...currentDraft,
        profile: {
          ...currentDraft.profile,
          work_authorization: {
            ...currentDraft.profile.work_authorization,
            citizenship_country_code: countryCode,
            citizenship_country_label: selectedCountryLabel,
          },
        },
      };
    });
  }

  function handleProfileEducationEntryFieldUpdate(
    index: number,
    fieldName: keyof CandidateEducationEntryDto,
    value: string | boolean,
  ): void {
    if (profileDraft === null) {
      return;
    }
    const updatedEntries = profileDraft.profile.education_entries.map((entry, entryIndex) => {
      if (entryIndex !== index) {
        return entry;
      }
      return {
        ...entry,
        [fieldName]: value,
      };
    });
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        education_entries: updatedEntries,
      },
    });
  }

  function handleProfileEducationEntryHighlightsUpdate(index: number, value: string): void {
    if (profileDraft === null) {
      return;
    }
    const updatedEntries = profileDraft.profile.education_entries.map((entry, entryIndex) => {
      if (entryIndex !== index) {
        return entry;
      }
      return {
        ...entry,
        highlights: linesToList(value),
      };
    });
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        education_entries: updatedEntries,
      },
    });
  }

  function addEducationEntry(): void {
    if (profileDraft === null) {
      return;
    }
    const existingIds = profileDraft.profile.education_entries.map((entry) => entry.id);
    const entryId = nextGeneratedId("education", existingIds);
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        education_entries: [
          ...profileDraft.profile.education_entries,
          buildDefaultEducationEntry(entryId),
        ],
      },
    });
  }

  function removeEducationEntry(index: number): void {
    if (profileDraft === null) {
      return;
    }
    updateProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        education_entries: profileDraft.profile.education_entries.filter(
          (_entry, entryIndex) => entryIndex !== index,
        ),
      },
    });
  }

  function handleProfileGuidedSave(): void {
    if (profileDraft === null) {
      return;
    }
    profileStructuredMutation.mutate({
      profile: profileDraft.profile,
      search_defaults: profileDraft.search_defaults,
      prompt_context: profileDraft.prompt_context,
    });
  }

  function handleProfileYamlSave(): void {
    profileYamlMutation.mutate(profileYamlDraft);
  }

  function handleProfileYamlUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    profileUploadMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeYamlUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    resumeUploadMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeTexUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    resumeTexMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeLayoutUpdate(
    fieldName: keyof ResumeContentDto["layout"],
    value: string,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const parsedValue = Number.parseFloat(value);
    if (!Number.isFinite(parsedValue)) {
      return;
    }
    updateResumeDraft({
      ...resumeDraft,
      layout: {
        ...resumeDraft.layout,
        [fieldName]: parsedValue,
      },
    });
  }

  function handleExperienceListingFieldUpdate(
    index: number,
    fieldName: "id" | "title" | "date_range" | "organization" | "enabled",
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.experience.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      return {
        ...listing,
        [fieldName]: value,
      };
    });
    updateResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: updatedListings,
      },
    });
  }

  function handleExperienceBulletsUpdate(index: number, value: string): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.experience.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      const nextBullets = linesToList(value).map((line, lineIndex) => ({
        id: `${listing.id || "exp"}_bullet_${lineIndex + 1}`,
        text: line,
      }));
      return {
        ...listing,
        bullets: nextBullets,
      };
    });
    updateResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: updatedListings,
      },
    });
  }

  function addExperienceListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.experience.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("exp_new", existingIds);
    const nextListings = [
      ...resumeDraft.experience.listings,
      {
        id: nextId,
        enabled: true,
        title: "New Experience Role",
        date_range: "MM. YYYY -- MM. YYYY",
        organization: "Organization",
        bullets: [
          {
            id: `${nextId}_bullet_1`,
            text: "Add impact-focused bullet text here.",
          },
        ],
      },
    ];
    updateResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: nextListings,
      },
    });
  }

  function removeExperienceListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    updateResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: resumeDraft.experience.listings.filter(
          (_listing, listingIndex) => listingIndex !== index,
        ),
      },
    });
  }

  function handleProjectListingFieldUpdate(
    index: number,
    fieldName: "id" | "title" | "date_range" | "tech_stack" | "enabled",
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.projects.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      return {
        ...listing,
        [fieldName]: value,
      };
    });
    updateResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: updatedListings,
      },
    });
  }

  function handleProjectBulletsUpdate(index: number, value: string): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.projects.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      const nextBullets = linesToList(value).map((line, lineIndex) => ({
        id: `${listing.id || "project"}_bullet_${lineIndex + 1}`,
        text: line,
      }));
      return {
        ...listing,
        bullets: nextBullets,
      };
    });
    updateResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: updatedListings,
      },
    });
  }

  function addProjectListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.projects.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("proj_new", existingIds);
    const nextListings = [
      ...resumeDraft.projects.listings,
      {
        id: nextId,
        enabled: true,
        title: "New Project",
        tech_stack: "Tech stack",
        date_range: "MM. YYYY -- MM. YYYY",
        bullets: [
          {
            id: `${nextId}_bullet_1`,
            text: "Add measurable project bullet text here.",
          },
        ],
      },
    ];
    updateResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: nextListings,
      },
    });
  }

  function removeProjectListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    updateResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: resumeDraft.projects.listings.filter(
          (_listing, listingIndex) => listingIndex !== index,
        ),
      },
    });
  }

  function handleSkillListingUpdate(
    index: number,
    fieldName: keyof ResumeSkillListingDto,
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.skills_achievements.listings.map(
      (listing, listingIndex) => {
        if (listingIndex !== index) {
          return listing;
        }
        return {
          ...listing,
          [fieldName]: value,
        };
      },
    );
    updateResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: updatedListings,
      },
    });
  }

  function addSkillListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.skills_achievements.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("skill_new", existingIds);
    const nextListings = [
      ...resumeDraft.skills_achievements.listings,
      {
        id: nextId,
        enabled: true,
        category: "Category",
        text: "Skill text",
      },
    ];
    updateResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: nextListings,
      },
    });
  }

  function removeSkillListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    updateResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: resumeDraft.skills_achievements.listings.filter(
          (_listing, listingIndex) => listingIndex !== index,
        ),
      },
    });
  }

  function handleResumeGuidedSave(): void {
    if (resumeDraft === null) {
      return;
    }
    resumeStructuredMutation.mutate(resumeDraft);
  }

  function handleResumeYamlSave(): void {
    resumeYamlMutation.mutate(resumeYamlDraft);
  }

  function handleServiceTierSelection(nextTier: ServiceTierDto): void {
    const missingKeys = getMissingKeysForTier(nextTier, configuredApiKeyMap);
    if (nextTier !== "base" && missingKeys.length > 0) {
      setTierFeedback({
        type: "error",
        message: `Cannot select ${nextTier.toUpperCase()}. Missing: ${missingKeys.join(", ")}.`,
      });
      return;
    }
    setSelectedServiceTier(nextTier);
    setIsTierDirty(true);
  }

  function handleServiceTierSave(): void {
    if (selectedServiceTier !== "base" && selectedTierMissingKeys.length > 0) {
      setTierFeedback({
        type: "error",
        message: `Cannot save ${selectedServiceTier.toUpperCase()}. Missing: ${selectedTierMissingKeys.join(", ")}.`,
      });
      return;
    }
    tierMutation.mutate(selectedServiceTier);
  }

  function startApiKeyEdit(keyName: ApiKeyNameDto): void {
    setEditingApiKeyName(keyName);
    setEditingApiKeyValue("");
    setApiKeyFeedback(null);
  }

  function cancelApiKeyEdit(): void {
    setEditingApiKeyName(null);
    setEditingApiKeyValue("");
  }

  function handleApiKeySave(keyName: ApiKeyNameDto): void {
    if (editingApiKeyValue.trim() === "") {
      setApiKeyFeedback({
        type: "error",
        message: `${keyName} cannot be empty.`,
      });
      return;
    }
    apiKeyUpsertMutation.mutate({
      keyName,
      keyValue: editingApiKeyValue.trim(),
    });
  }

  function handleApiKeyDelete(keyName: ApiKeyNameDto): void {
    if (!window.confirm(`Delete ${keyName}? This action cannot be undone.`)) {
      return;
    }
    apiKeyDeleteMutation.mutate(keyName);
  }

  const parsedBudgetInput = Number.parseFloat(budgetInput);
  const isBudgetInputValid = Number.isFinite(parsedBudgetInput) && parsedBudgetInput >= 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Settings
            </h2>
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Configure budget, pipeline depth, candidate context, and source filters in one place.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {TOP_LEVEL_TABS.map((tab) => (
              <TabButton
                key={tab.id}
                active={activeTopLevelTab === tab.id}
                label={tab.label}
                onClick={() => handleTopLevelTabChange(tab.id)}
              />
            ))}
          </div>
        </div>

        {hasUnsavedChanges && (
          <div
            className="rounded-xl border px-4 py-3 text-sm"
            style={{
              borderColor: COLOR_WARNING,
              color: COLOR_ON_WARNING_CONTAINER,
              backgroundColor: COLOR_WARNING_CONTAINER,
            }}
          >
            You have unsaved changes. Save before switching tabs to avoid losing edits.
          </div>
        )}
      </section>

      {activeTopLevelTab === "general" && (
        <>
          <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                  Monthly Budget
                </h3>
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Set a monthly spend cap for all automation-related API usage.
                </p>
              </div>
              <button
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleBudgetSave}
                disabled={!isBudgetDirty || !isBudgetInputValid || budgetMutation.isPending}
              >
                {budgetMutation.isPending ? "Saving..." : "Save Budget"}
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
                <p
                  className="text-xs font-semibold uppercase tracking-wide"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                >
                  Monthly Limit ($)
                </p>
                <input
                  className="mt-1 w-full bg-transparent text-lg font-bold focus:outline-none"
                  style={{ color: COLOR_ON_SURFACE }}
                  type="number"
                  min="0"
                  step="0.01"
                  value={budgetInput}
                  onChange={(event) => {
                    setBudgetInput(event.target.value);
                    setIsBudgetDirty(true);
                  }}
                />
              </div>
              <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
                <p
                  className="text-xs font-semibold uppercase tracking-wide"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                >
                  Spent This Month
                </p>
                <p className="mt-1 text-lg font-bold">
                  {formatUsd(budgetQuery.data?.spent_usd ?? 0)}
                </p>
              </div>
              <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
                <p
                  className="text-xs font-semibold uppercase tracking-wide"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                >
                  Remaining
                </p>
                <p className="mt-1 text-lg font-bold">
                  {formatUsd(budgetQuery.data?.remaining_usd ?? 0)}
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="h-2 rounded-full bg-surface-container overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${budgetUsedPct}%`, backgroundColor: budgetProgressColor }}
                />
              </div>
              <p className="text-right text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                {budgetUsedPct}% consumed
              </p>
            </div>
            {budgetMutation.isError && (
              <InlineErrorText
                message={`Budget save failed: ${getErrorMessage(budgetMutation.error)}`}
              />
            )}
          </section>

          <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
            <div>
              <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                API Keys
              </h3>
              <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Manage provider and service secrets. Keys are write-only and cannot be read after
                saving.
              </p>
            </div>

            {apiKeysQuery.isError && (
              <div
                className="rounded-xl border px-4 py-3 text-sm"
                style={{
                  borderColor: COLOR_WARNING,
                  color: COLOR_ON_WARNING_CONTAINER,
                  backgroundColor: COLOR_WARNING_CONTAINER,
                }}
              >
                API key status endpoint is not available yet. UI is ready; backend wiring is still
                required.
              </div>
            )}

            <div className="space-y-3">
              {API_KEYS.map((apiKey) => {
                const isConfigured =
                  normalizedApiKeys.find((entry) => entry.name === apiKey.name)?.configured ??
                  false;
                const isEditing = editingApiKeyName === apiKey.name;
                const isSavingThisKey =
                  apiKeyUpsertMutation.isPending &&
                  apiKeyUpsertMutation.variables?.keyName === apiKey.name;
                const isDeletingThisKey =
                  apiKeyDeleteMutation.isPending && apiKeyDeleteMutation.variables === apiKey.name;

                return (
                  <div
                    key={apiKey.name}
                    className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white border border-outline-variant/30">
                          <span
                            className="material-symbols-outlined text-base"
                            style={{ color: COLOR_PRIMARY }}
                          >
                            {apiKey.icon}
                          </span>
                        </div>
                        <div>
                          <p className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE }}>
                            {apiKey.name}
                          </p>
                          <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                            {isConfigured ? "● Configured" : "○ Not configured"}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        {!isConfigured && !isEditing && (
                          <button
                            className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: COLOR_PRIMARY }}
                            onClick={() => startApiKeyEdit(apiKey.name)}
                            disabled={isSavingThisKey || isDeletingThisKey}
                          >
                            Add Key
                          </button>
                        )}

                        {isConfigured && !isEditing && (
                          <>
                            <button
                              className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
                              style={{ color: COLOR_ON_SURFACE_VARIANT }}
                              onClick={() => startApiKeyEdit(apiKey.name)}
                              disabled={isSavingThisKey || isDeletingThisKey}
                            >
                              Update
                            </button>
                            <button
                              className="text-sm font-semibold disabled:opacity-50"
                              style={{ color: COLOR_ERROR }}
                              onClick={() => handleApiKeyDelete(apiKey.name)}
                              disabled={isDeletingThisKey || isSavingThisKey}
                            >
                              {isDeletingThisKey ? "Deleting..." : "Delete"}
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                      {apiKey.description}
                    </p>

                    {isEditing && (
                      <div className="rounded-lg border border-outline-variant/40 bg-white p-3 space-y-3">
                        <label
                          className="block text-xs font-semibold"
                          style={{ color: COLOR_ON_SURFACE_VARIANT }}
                        >
                          Secret Value
                          <input
                            className="mt-2 w-full rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 text-sm"
                            style={{ WebkitTextSecurity: "disc" } as import("react").CSSProperties}
                            type="password"
                            autoComplete="new-password"
                            placeholder="sk-..."
                            value={editingApiKeyValue}
                            onChange={(event) => {
                              setEditingApiKeyValue(event.target.value);
                            }}
                          />
                        </label>
                        <div className="flex items-center justify-end gap-3">
                          <button
                            className="rounded-lg px-3 py-2 text-sm font-semibold"
                            style={{ color: COLOR_ON_SURFACE_VARIANT }}
                            onClick={cancelApiKeyEdit}
                            disabled={isSavingThisKey}
                          >
                            Cancel
                          </button>
                          <button
                            className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: COLOR_PRIMARY }}
                            onClick={() => handleApiKeySave(apiKey.name)}
                            disabled={isSavingThisKey || editingApiKeyValue.trim() === ""}
                          >
                            {isSavingThisKey ? "Saving..." : "Save Key"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {apiKeyFeedback !== null && apiKeyFeedback.type === "success" && (
              <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
                {apiKeyFeedback.message}
              </p>
            )}
            {apiKeyFeedback !== null && apiKeyFeedback.type === "error" && (
              <InlineErrorText message={apiKeyFeedback.message} />
            )}
          </section>

          <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
            <div>
              <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                Service Tier
              </h3>
              <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Choose how much of the pipeline runs. Base includes discovery + gate logic and still
                works without provider keys.
              </p>
            </div>

            <div
              className="rounded-xl border px-4 py-3 text-sm"
              style={{
                borderColor: COLOR_WARNING,
                color: COLOR_ON_WARNING_CONTAINER,
                backgroundColor: COLOR_WARNING_CONTAINER,
              }}
            >
              Changing tiers requires restarting Docker Compose services. Check the deployment
              README for restart steps.
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              {SERVICE_TIER_CARDS.map((tierCard) => {
                const missingKeys = getMissingKeysForTier(tierCard.tier, configuredApiKeyMap);
                const isBlocked = tierCard.tier !== "base" && missingKeys.length > 0;
                const isSelected = selectedServiceTier === tierCard.tier;
                return (
                  <button
                    key={tierCard.tier}
                    type="button"
                    className="rounded-xl border p-4 text-left space-y-3 transition-colors disabled:opacity-70"
                    style={{
                      borderColor: isSelected ? COLOR_PRIMARY : `${COLOR_OUTLINE_VARIANT}80`,
                      borderWidth: isSelected ? 2 : 1,
                      backgroundColor: isSelected ? COLOR_PRIMARY_FIXED : "#ffffff",
                    }}
                    onClick={() => {
                      handleServiceTierSelection(tierCard.tier);
                    }}
                    disabled={isBlocked || tierMutation.isPending}
                    title={
                      isBlocked ? `Missing required keys: ${missingKeys.join(", ")}` : undefined
                    }
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="material-symbols-outlined text-base"
                          style={{ color: COLOR_PRIMARY }}
                        >
                          {tierCard.icon}
                        </span>
                        <p className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                          {tierCard.title}
                        </p>
                      </div>
                      {tierCard.badge !== undefined && (
                        <span
                          className="rounded-full px-2 py-1 text-[10px] font-bold text-white"
                          style={{ backgroundColor: COLOR_PRIMARY }}
                        >
                          {tierCard.badge}
                        </span>
                      )}
                    </div>

                    <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                      {tierCard.description}
                    </p>

                    <ul className="space-y-1">
                      {tierCard.features.map((feature) => (
                        <li
                          key={`${tierCard.tier}-${feature}`}
                          className="text-xs"
                          style={{ color: COLOR_ON_SURFACE_VARIANT }}
                        >
                          ✓ {feature}
                        </li>
                      ))}
                    </ul>

                    {isBlocked && (
                      <p className="text-xs font-semibold" style={{ color: COLOR_ERROR }}>
                        Missing keys: {missingKeys.join(", ")}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end">
              <button
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleServiceTierSave}
                disabled={
                  !isTierDirty ||
                  tierMutation.isPending ||
                  (selectedServiceTier !== "base" && selectedTierMissingKeys.length > 0)
                }
              >
                {tierMutation.isPending ? "Saving..." : "Save Tier"}
              </button>
            </div>

            {tierFeedback !== null && tierFeedback.type === "success" && (
              <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
                {tierFeedback.message}
              </p>
            )}
            {tierFeedback !== null && tierFeedback.type === "error" && (
              <InlineErrorText message={tierFeedback.message} />
            )}
          </section>
        </>
      )}

      {activeTopLevelTab === "ai-provider" && (
        <section className="rounded-2xl border border-outline-variant/30 bg-white p-6">
          <AIProviderSettings />
        </section>
      )}

      {activeTopLevelTab === "candidate" && (
        <>
          <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                  Candidate Profile
                </h3>
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  This profile is always available and drives gate-agent decision quality.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <TabButton
                  active={candidateTab === "guided"}
                  label="Guided"
                  onClick={() => setCandidateTab("guided")}
                />
                <TabButton
                  active={candidateTab === "yaml"}
                  label="Advanced YAML"
                  onClick={() => setCandidateTab("yaml")}
                />
                <TabButton
                  active={candidateTab === "files"}
                  label="File Actions"
                  onClick={() => setCandidateTab("files")}
                />
              </div>
            </div>

            {candidateTab === "guided" && profileDraft !== null && (
              <div className="space-y-6">
                <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
                  <h4
                    className="text-sm font-bold uppercase tracking-wide"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    Core Context
                  </h4>
                  <LabeledTextarea
                    label="Summary"
                    value={profileDraft.profile.summary}
                    onChange={(value) => handleProfileScalarUpdate("summary", value)}
                    rows={4}
                    helperText={`${profileDraft.profile.summary.trim().length} character(s)`}
                  />

                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                        Contact
                      </h5>
                      <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                        Standard fields reused across job applications.
                      </p>
                    </div>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      <LabeledInput
                        label="Full Name"
                        value={profileDraft.profile.contact.full_name}
                        onChange={(value) => handleProfileContactFieldUpdate("full_name", value)}
                      />
                      <LabeledInput
                        label="Email"
                        value={profileDraft.profile.contact.email}
                        onChange={(value) => handleProfileContactFieldUpdate("email", value)}
                      />
                      <LabeledInput
                        label="Phone"
                        value={profileDraft.profile.contact.phone}
                        onChange={(value) => handleProfileContactFieldUpdate("phone", value)}
                      />
                      <LabeledInput
                        label="City"
                        value={profileDraft.profile.contact.city}
                        onChange={(value) => handleProfileContactFieldUpdate("city", value)}
                      />
                      <LabeledInput
                        label="State / Region"
                        value={profileDraft.profile.contact.state_or_region}
                        onChange={(value) =>
                          handleProfileContactFieldUpdate("state_or_region", value)
                        }
                      />
                      <LabeledSelect
                        label="Country"
                        value={profileDraft.profile.contact.country_code}
                        onChange={(value) => handleProfileContactCountryUpdate(value)}
                        options={[
                          { value: "", label: "Select country" },
                          ...countryOptions.map((countryOption) => ({
                            value: countryOption.code,
                            label: countryOption.label,
                          })),
                        ]}
                      />
                      <LabeledInput
                        label="LinkedIn URL"
                        value={profileDraft.profile.contact.linkedin_url}
                        onChange={(value) => handleProfileContactFieldUpdate("linkedin_url", value)}
                      />
                      <LabeledInput
                        label="GitHub URL"
                        value={profileDraft.profile.contact.github_url}
                        onChange={(value) => handleProfileContactFieldUpdate("github_url", value)}
                      />
                      <LabeledInput
                        label="Portfolio URL"
                        value={profileDraft.profile.contact.portfolio_url}
                        onChange={(value) =>
                          handleProfileContactFieldUpdate("portfolio_url", value)
                        }
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                      Work Authorization
                    </h5>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                      <LabeledSelect
                        label="Citizenship"
                        value={profileDraft.profile.work_authorization.citizenship_country_code}
                        onChange={(value) => handleProfileCitizenshipCountryUpdate(value)}
                        options={[
                          { value: "", label: "Select citizenship country" },
                          ...countryOptions.map((countryOption) => ({
                            value: countryOption.code,
                            label: countryOption.label,
                          })),
                        ]}
                        helperText="United States is pinned first for faster selection."
                      />
                      <LabeledSelect
                        label="Authorized to work in U.S.?"
                        value={profileDraft.profile.work_authorization.authorized_to_work_us}
                        onChange={(value) =>
                          handleProfileWorkAuthorizationFieldUpdate("authorized_to_work_us", value)
                        }
                        options={YES_NO_UNKNOWN_OPTIONS}
                      />
                      <LabeledSelect
                        label="Need sponsorship now or later?"
                        value={
                          profileDraft.profile.work_authorization.requires_sponsorship_now_or_future
                        }
                        onChange={(value) =>
                          handleProfileWorkAuthorizationFieldUpdate(
                            "requires_sponsorship_now_or_future",
                            value,
                          )
                        }
                        options={YES_NO_UNKNOWN_OPTIONS}
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                        Education
                      </h5>
                      <button
                        className="text-sm font-semibold"
                        style={{ color: COLOR_PRIMARY }}
                        onClick={addEducationEntry}
                      >
                        + Add Education
                      </button>
                    </div>
                    <LabeledInput
                      label="Education Summary"
                      value={profileDraft.profile.education_summary}
                      onChange={(value) => handleProfileScalarUpdate("education_summary", value)}
                    />
                    {profileDraft.profile.education_entries.map((entry, entryIndex) => (
                      <div
                        key={entry.id}
                        className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3"
                      >
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                          <LabeledInput
                            label="School"
                            value={entry.school}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(entryIndex, "school", value)
                            }
                          />
                          <LabeledSelect
                            label="Degree Level"
                            value={entry.degree_level}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(
                                entryIndex,
                                "degree_level",
                                value,
                              )
                            }
                            options={DEGREE_LEVEL_OPTIONS}
                          />
                          <LabeledInput
                            label="Degree Name"
                            value={entry.degree_name}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(
                                entryIndex,
                                "degree_name",
                                value,
                              )
                            }
                          />
                          <LabeledInput
                            label="Field of Study"
                            value={entry.field_of_study}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(
                                entryIndex,
                                "field_of_study",
                                value,
                              )
                            }
                          />
                          <LabeledInput
                            label="Location"
                            value={entry.location}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(entryIndex, "location", value)
                            }
                          />
                          <LabeledInput
                            label="GPA (optional)"
                            value={entry.gpa}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(entryIndex, "gpa", value)
                            }
                          />
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
                          <LabeledSelect
                            label="Start Month"
                            value={entry.start_month}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(
                                entryIndex,
                                "start_month",
                                value,
                              )
                            }
                            options={MONTH_OPTIONS}
                          />
                          <LabeledInput
                            label="Start Year"
                            value={entry.start_year}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(
                                entryIndex,
                                "start_year",
                                value,
                              )
                            }
                          />
                          <LabeledSelect
                            label="End Month"
                            value={entry.end_month}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(entryIndex, "end_month", value)
                            }
                            options={MONTH_OPTIONS}
                          />
                          <LabeledInput
                            label="End Year"
                            value={entry.end_year}
                            onChange={(value) =>
                              handleProfileEducationEntryFieldUpdate(entryIndex, "end_year", value)
                            }
                          />
                          <label
                            className="mt-6 text-xs font-semibold"
                            style={{ color: COLOR_ON_SURFACE_VARIANT }}
                          >
                            <input
                              type="checkbox"
                              checked={entry.is_current}
                              onChange={(event) =>
                                handleProfileEducationEntryFieldUpdate(
                                  entryIndex,
                                  "is_current",
                                  event.target.checked,
                                )
                              }
                            />{" "}
                            Currently enrolled
                          </label>
                        </div>
                        <LabeledTextarea
                          label="Highlights (one per line)"
                          value={listToLines(entry.highlights)}
                          onChange={(value) =>
                            handleProfileEducationEntryHighlightsUpdate(entryIndex, value)
                          }
                          rows={3}
                          helperText={`${entry.highlights.length} item(s)`}
                        />
                        <div className="flex justify-end">
                          <button
                            className="text-xs font-semibold"
                            style={{ color: COLOR_ERROR }}
                            onClick={() => removeEducationEntry(entryIndex)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
                  <h4
                    className="text-sm font-bold uppercase tracking-wide"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    Role Targeting
                  </h4>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <LabeledTextarea
                      label="Target Roles (one per line)"
                      value={listToLines(profileDraft.profile.target_roles)}
                      onChange={(value) => handleProfileListUpdate("target_roles", value)}
                      helperText={`${countListItems(listToLines(profileDraft.profile.target_roles))} item(s)`}
                    />
                    <LabeledTextarea
                      label="Strongest Areas (one per line)"
                      value={listToLines(profileDraft.profile.strongest_areas)}
                      onChange={(value) => handleProfileListUpdate("strongest_areas", value)}
                      helperText={`${countListItems(listToLines(profileDraft.profile.strongest_areas))} item(s)`}
                    />
                    <LabeledTextarea
                      label="Experience Highlights (one per line)"
                      value={listToLines(profileDraft.profile.experience_highlights)}
                      onChange={(value) => handleProfileListUpdate("experience_highlights", value)}
                      helperText={`${countListItems(listToLines(profileDraft.profile.experience_highlights))} item(s)`}
                    />
                    <LabeledTextarea
                      label="Search Terms (one per line)"
                      value={listToLines(profileDraft.search_defaults.job_board_search_terms)}
                      onChange={(value) => {
                        updateProfileDraft({
                          ...profileDraft,
                          search_defaults: { job_board_search_terms: linesToList(value) },
                        });
                      }}
                      helperText={`${countListItems(listToLines(profileDraft.search_defaults.job_board_search_terms))} item(s)`}
                    />
                  </div>
                </div>

                <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
                  <h4
                    className="text-sm font-bold uppercase tracking-wide"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    Decision Rules
                  </h4>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <LabeledTextarea
                      label="Hard Filters (one per line)"
                      value={listToLines(profileDraft.profile.hard_filters)}
                      onChange={(value) => handleProfileListUpdate("hard_filters", value)}
                      helperText={`${countListItems(listToLines(profileDraft.profile.hard_filters))} item(s)`}
                    />
                    <LabeledTextarea
                      label="Preferences (one per line)"
                      value={listToLines(profileDraft.profile.preferences)}
                      onChange={(value) => handleProfileListUpdate("preferences", value)}
                      helperText={`${countListItems(listToLines(profileDraft.profile.preferences))} item(s)`}
                    />
                  </div>
                </div>

                <LabeledTextarea
                  label="Prompt Context Override (optional)"
                  value={profileDraft.prompt_context ?? ""}
                  onChange={(value) => {
                    updateProfileDraft({
                      ...profileDraft,
                      prompt_context: value.trim() === "" ? null : value,
                    });
                  }}
                  rows={6}
                  helperText="Additional context injected into AI prompts."
                />

                <div className="flex justify-end">
                  <button
                    className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                    onClick={handleProfileGuidedSave}
                    disabled={profileStructuredMutation.isPending || !isProfileDirty}
                  >
                    {profileStructuredMutation.isPending ? "Saving..." : "Save Profile"}
                  </button>
                </div>
                {profileStructuredMutation.isError && (
                  <InlineErrorText
                    message={`Profile save failed: ${getErrorMessage(profileStructuredMutation.error)}`}
                  />
                )}
              </div>
            )}

            {candidateTab === "yaml" && (
              <div className="space-y-4">
                <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                  Advanced: editing YAML here overrides guided form values.
                </p>
                <YamlEditor
                  modelPath={PROFILE_EDITOR_MODEL_URI}
                  value={profileYamlDraft}
                  onChange={updateProfileYamlDraft}
                />
                <div className="flex justify-end">
                  <button
                    className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                    onClick={handleProfileYamlSave}
                    disabled={profileYamlMutation.isPending || !isProfileDirty}
                  >
                    {profileYamlMutation.isPending ? "Saving..." : "Save YAML"}
                  </button>
                </div>
                {profileYamlMutation.isError && (
                  <InlineErrorText
                    message={`YAML save failed: ${getErrorMessage(profileYamlMutation.error)}`}
                  />
                )}
              </div>
            )}

            {candidateTab === "files" && (
              <div className="space-y-4">
                <SettingsFileCard
                  title="Candidate Profile YAML"
                  subtitle={
                    profileMetadata?.modified_at
                      ? new Date(profileMetadata.modified_at).toLocaleString()
                      : "No file timestamp"
                  }
                  downloadUrl={getProfileDownloadUrl()}
                />
                <input
                  ref={profileYamlInputRef}
                  type="file"
                  accept=".yaml,.yml,text/yaml,application/x-yaml"
                  className="hidden"
                  onChange={handleProfileYamlUpload}
                />
                <button
                  className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  onClick={() => profileYamlInputRef.current?.click()}
                  disabled={profileUploadMutation.isPending}
                >
                  {profileUploadMutation.isPending ? "Uploading..." : "Replace Profile YAML"}
                </button>
                {profileUploadMutation.isError && (
                  <InlineErrorText
                    message={`Upload failed: ${getErrorMessage(profileUploadMutation.error)}`}
                  />
                )}
              </div>
            )}
          </section>

          {canOpenResumeEditor ? (
            <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                    Resume Editor
                  </h3>
                  <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    Resume editing is enabled for LaTeX and Full tiers.
                  </p>
                  <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
                    {resumeCountsText}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <TabButton
                    active={resumeTab === "guided"}
                    label="Guided"
                    onClick={() => setResumeTab("guided")}
                  />
                  <TabButton
                    active={resumeTab === "yaml"}
                    label="Advanced YAML"
                    onClick={() => setResumeTab("yaml")}
                  />
                  <TabButton
                    active={resumeTab === "tex"}
                    label="Upload TeX"
                    onClick={() => setResumeTab("tex")}
                  />
                  <TabButton
                    active={resumeTab === "files"}
                    label="File Actions"
                    onClick={() => setResumeTab("files")}
                  />
                </div>
              </div>

              {resumeTab === "guided" && resumeDraft !== null && (
                <div className="space-y-6">
                  <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4">
                    <h4 className="text-sm font-bold uppercase tracking-wide">
                      Locked Sections (Read-Only)
                    </h4>
                    <p className="mt-2 text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                      Personal and education sections are locked by resume policy.
                    </p>
                    <p className="mt-3 text-sm">
                      <strong>{resumeDraft.personal.name}</strong> • {resumeDraft.personal.email} •{" "}
                      {resumeDraft.personal.phone}
                    </p>
                    {resumeDraft.education.entries.map((entry) => (
                      <div key={entry.id} className="mt-2 text-sm">
                        <p>
                          <strong>{entry.institution}</strong> ({entry.date_range})
                        </p>
                        <p>{entry.degree}</p>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
                    <h4 className="text-sm font-bold uppercase tracking-wide">Layout Knobs</h4>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                      {Object.entries(resumeDraft.layout).map(([fieldName, fieldValue]) => (
                        <label key={fieldName} className="text-xs font-semibold">
                          {fieldName}
                          <input
                            className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
                            type="number"
                            step="0.01"
                            value={fieldValue}
                            onChange={(event) =>
                              handleResumeLayoutUpdate(
                                fieldName as keyof ResumeContentDto["layout"],
                                event.target.value,
                              )
                            }
                          />
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-bold uppercase tracking-wide">Work Experience</h4>
                      <button
                        className="text-sm font-semibold"
                        style={{ color: COLOR_PRIMARY }}
                        onClick={addExperienceListing}
                      >
                        + Add Experience
                      </button>
                    </div>
                    {resumeDraft.experience.listings.map((listing, index) => (
                      <div
                        key={`experience-${index}`}
                        className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
                      >
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                          <LabeledInput
                            label="ID"
                            value={listing.id}
                            onChange={(value) =>
                              handleExperienceListingFieldUpdate(index, "id", value)
                            }
                          />
                          <LabeledInput
                            label="Title"
                            value={listing.title}
                            onChange={(value) =>
                              handleExperienceListingFieldUpdate(index, "title", value)
                            }
                          />
                          <LabeledInput
                            label="Date Range"
                            value={listing.date_range}
                            onChange={(value) =>
                              handleExperienceListingFieldUpdate(index, "date_range", value)
                            }
                          />
                          <LabeledInput
                            label="Company"
                            value={listing.organization}
                            onChange={(value) =>
                              handleExperienceListingFieldUpdate(index, "organization", value)
                            }
                          />
                        </div>
                        <LabeledTextarea
                          label="Bullet Points (one per line)"
                          value={listing.bullets.map((bullet) => bullet.text).join("\n")}
                          onChange={(value) => handleExperienceBulletsUpdate(index, value)}
                          rows={4}
                        />
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-semibold">
                            <input
                              type="checkbox"
                              checked={listing.enabled}
                              onChange={(event) =>
                                handleExperienceListingFieldUpdate(
                                  index,
                                  "enabled",
                                  event.target.checked,
                                )
                              }
                            />{" "}
                            Enabled
                          </label>
                          <button
                            className="text-xs font-semibold"
                            style={{ color: COLOR_ERROR }}
                            onClick={() => removeExperienceListing(index)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-bold uppercase tracking-wide">Projects</h4>
                      <button
                        className="text-sm font-semibold"
                        style={{ color: COLOR_PRIMARY }}
                        onClick={addProjectListing}
                      >
                        + Add Project
                      </button>
                    </div>
                    {resumeDraft.projects.listings.map((listing, index) => (
                      <div
                        key={`project-${index}`}
                        className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
                      >
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                          <LabeledInput
                            label="ID"
                            value={listing.id}
                            onChange={(value) =>
                              handleProjectListingFieldUpdate(index, "id", value)
                            }
                          />
                          <LabeledInput
                            label="Name"
                            value={listing.title}
                            onChange={(value) =>
                              handleProjectListingFieldUpdate(index, "title", value)
                            }
                          />
                          <LabeledInput
                            label="Tech Stack"
                            value={listing.tech_stack}
                            onChange={(value) =>
                              handleProjectListingFieldUpdate(index, "tech_stack", value)
                            }
                          />
                          <LabeledInput
                            label="Date"
                            value={listing.date_range}
                            onChange={(value) =>
                              handleProjectListingFieldUpdate(index, "date_range", value)
                            }
                          />
                        </div>
                        <LabeledTextarea
                          label="Bullet Points (one per line)"
                          value={listing.bullets.map((bullet) => bullet.text).join("\n")}
                          onChange={(value) => handleProjectBulletsUpdate(index, value)}
                          rows={3}
                        />
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-semibold">
                            <input
                              type="checkbox"
                              checked={listing.enabled}
                              onChange={(event) =>
                                handleProjectListingFieldUpdate(
                                  index,
                                  "enabled",
                                  event.target.checked,
                                )
                              }
                            />{" "}
                            Enabled
                          </label>
                          <button
                            className="text-xs font-semibold"
                            style={{ color: COLOR_ERROR }}
                            onClick={() => removeProjectListing(index)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-bold uppercase tracking-wide">
                        Skills & Achievements
                      </h4>
                      <button
                        className="text-sm font-semibold"
                        style={{ color: COLOR_PRIMARY }}
                        onClick={addSkillListing}
                      >
                        + Add Skill Row
                      </button>
                    </div>
                    {resumeDraft.skills_achievements.listings.map((listing, index) => (
                      <div
                        key={`skill-${index}`}
                        className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
                      >
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                          <LabeledInput
                            label="ID"
                            value={listing.id}
                            onChange={(value) => handleSkillListingUpdate(index, "id", value)}
                          />
                          <LabeledInput
                            label="Category"
                            value={listing.category}
                            onChange={(value) => handleSkillListingUpdate(index, "category", value)}
                          />
                          <LabeledInput
                            label="Text"
                            value={listing.text}
                            onChange={(value) => handleSkillListingUpdate(index, "text", value)}
                          />
                        </div>
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-semibold">
                            <input
                              type="checkbox"
                              checked={listing.enabled}
                              onChange={(event) =>
                                handleSkillListingUpdate(index, "enabled", event.target.checked)
                              }
                            />{" "}
                            Enabled
                          </label>
                          <button
                            className="text-xs font-semibold"
                            style={{ color: COLOR_ERROR }}
                            onClick={() => removeSkillListing(index)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="flex justify-end">
                    <button
                      className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                      style={{ backgroundColor: COLOR_PRIMARY }}
                      onClick={handleResumeGuidedSave}
                      disabled={resumeStructuredMutation.isPending || !isResumeDirty}
                    >
                      {resumeStructuredMutation.isPending ? "Saving..." : "Save Resume"}
                    </button>
                  </div>
                  {resumeStructuredMutation.isError && (
                    <InlineErrorText
                      message={`Resume save failed: ${getErrorMessage(resumeStructuredMutation.error)}`}
                    />
                  )}
                </div>
              )}

              {resumeTab === "yaml" && (
                <div className="space-y-4">
                  <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                    Advanced: edit raw resume YAML. Changes here override guided edits.
                  </p>
                  <YamlEditor
                    modelPath={RESUME_EDITOR_MODEL_URI}
                    value={resumeYamlDraft}
                    onChange={updateResumeYamlDraft}
                  />
                  <div className="flex justify-end">
                    <button
                      className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                      style={{ backgroundColor: COLOR_PRIMARY }}
                      onClick={handleResumeYamlSave}
                      disabled={resumeYamlMutation.isPending || !isResumeDirty}
                    >
                      {resumeYamlMutation.isPending ? "Saving..." : "Save YAML"}
                    </button>
                  </div>
                  {resumeYamlMutation.isError && (
                    <InlineErrorText
                      message={`YAML save failed: ${getErrorMessage(resumeYamlMutation.error)}`}
                    />
                  )}
                </div>
              )}

              {resumeTab === "tex" && (
                <div className="space-y-4">
                  <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    Upload a LaTeX resume source (`.tex`) and convert it into canonical YAML
                    automatically.
                  </p>
                  <input
                    ref={resumeTexInputRef}
                    type="file"
                    accept=".tex,text/plain"
                    className="hidden"
                    onChange={handleResumeTexUpload}
                  />
                  <button
                    className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
                    style={{ color: COLOR_ON_SURFACE_VARIANT }}
                    onClick={() => resumeTexInputRef.current?.click()}
                    disabled={resumeTexMutation.isPending}
                  >
                    {resumeTexMutation.isPending ? "Converting..." : "Upload TeX and Convert"}
                  </button>
                  {lastResumeMigrationSummary !== null && (
                    <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
                      Latest migration: {lastResumeMigrationSummary}
                    </p>
                  )}
                  {resumeTexMutation.isError && (
                    <InlineErrorText
                      message={`TeX conversion failed: ${getErrorMessage(resumeTexMutation.error)}`}
                    />
                  )}
                </div>
              )}

              {resumeTab === "files" && (
                <div className="space-y-4">
                  <SettingsFileCard
                    title="Resume YAML"
                    subtitle={
                      resumeMetadata?.modified_at
                        ? new Date(resumeMetadata.modified_at).toLocaleString()
                        : "No file timestamp"
                    }
                    downloadUrl={getResumeDownloadUrl()}
                  />
                  <input
                    ref={resumeYamlInputRef}
                    type="file"
                    accept=".yaml,.yml,text/yaml,application/x-yaml"
                    className="hidden"
                    onChange={handleResumeYamlUpload}
                  />
                  <button
                    className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
                    style={{ color: COLOR_ON_SURFACE_VARIANT }}
                    onClick={() => resumeYamlInputRef.current?.click()}
                    disabled={resumeUploadMutation.isPending}
                  >
                    {resumeUploadMutation.isPending ? "Uploading..." : "Replace Resume YAML"}
                  </button>
                  {resumeUploadMutation.isError && (
                    <InlineErrorText
                      message={`Upload failed: ${getErrorMessage(resumeUploadMutation.error)}`}
                    />
                  )}
                </div>
              )}
            </section>
          ) : (
            <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-4">
              <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                Resume Editor
              </h3>
              <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Resume editor is available only for LaTeX or Full tiers.
              </p>
              <div
                className="rounded-xl border px-4 py-3 text-sm"
                style={{
                  borderColor: COLOR_WARNING,
                  color: COLOR_ON_WARNING_CONTAINER,
                  backgroundColor: COLOR_WARNING_CONTAINER,
                }}
              >
                Select LaTeX or Full in <strong>General Settings → Service Tier</strong> to enable
                resume tailoring and review workflows.
              </div>
            </section>
          )}
        </>
      )}

      {activeTopLevelTab === "filters" && (
        <>
          <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
                  Company & Job Filters
                </h3>
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Configure filtering rules and discovery source lists used by the ingestion
                  pipeline.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <TabButton
                  active={activeFiltersTab === "guided"}
                  label="Guided"
                  onClick={() => handleFiltersTabChange("guided")}
                />
                <TabButton
                  active={activeFiltersTab === "filters"}
                  label="Advanced YAML"
                  onClick={() => handleFiltersTabChange("filters")}
                />
                <TabButton
                  active={activeFiltersTab === "sources"}
                  label="Company Sources"
                  onClick={() => handleFiltersTabChange("sources")}
                />
              </div>
            </div>

            {activeFiltersTab === "guided" && filtersGuidedDraft !== null && (
              <div className="space-y-6">
                {/* Hard Filters */}
                <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
                  <h4
                    className="text-sm font-bold uppercase tracking-wide"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    Hard Filters
                  </h4>
                  <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                    Jobs matching any hard filter are rejected before entering the database.
                  </p>

                  <div className="space-y-2">
                    <p className="text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                      Exclude Job Types
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {JOB_TYPES.map((jobType) => {
                        const isChecked = filtersGuidedDraft.hard_exclude_job_types.includes(jobType);
                        return (
                          <label
                            key={jobType}
                            className="flex items-center gap-1.5 text-xs cursor-pointer select-none"
                            style={{ color: COLOR_ON_SURFACE }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {
                                const next = isChecked
                                  ? filtersGuidedDraft.hard_exclude_job_types.filter(
                                      (t) => t !== jobType,
                                    )
                                  : [...filtersGuidedDraft.hard_exclude_job_types, jobType];
                                updateFiltersGuidedDraft({
                                  ...filtersGuidedDraft,
                                  hard_exclude_job_types: next,
                                });
                              }}
                            />
                            {jobType}
                          </label>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <LabeledTextarea
                      label={`Exclude Title Patterns (${countListItems(filtersGuidedDraft.hard_exclude_title_patterns)} patterns) — one regex per line`}
                      value={filtersGuidedDraft.hard_exclude_title_patterns}
                      rows={5}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_exclude_title_patterns: value,
                        })
                      }
                    />
                    <LabeledTextarea
                      label={`Require Title Patterns (${countListItems(filtersGuidedDraft.hard_require_title_patterns)} patterns) — one regex per line, leave empty to disable`}
                      value={filtersGuidedDraft.hard_require_title_patterns}
                      rows={5}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_require_title_patterns: value,
                        })
                      }
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <LabeledTextarea
                      label={`Exclude Locations (${countListItems(filtersGuidedDraft.hard_exclude_locations)} entries) — one substring per line`}
                      value={filtersGuidedDraft.hard_exclude_locations}
                      rows={3}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_exclude_locations: value,
                        })
                      }
                    />
                    <LabeledTextarea
                      label={`Exclude Companies (${countListItems(filtersGuidedDraft.hard_exclude_companies)} entries) — one per line`}
                      value={filtersGuidedDraft.hard_exclude_companies}
                      rows={3}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_exclude_companies: value,
                        })
                      }
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <LabeledInput
                      label="Max Days Old (0 = disabled)"
                      value={filtersGuidedDraft.hard_max_days_old}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_max_days_old: value,
                        })
                      }
                    />
                    <LabeledInput
                      label="Min Salary USD (0 = disabled)"
                      value={filtersGuidedDraft.hard_min_salary_usd}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_min_salary_usd: value,
                        })
                      }
                    />
                    <LabeledInput
                      label="Max Salary USD (0 = disabled)"
                      value={filtersGuidedDraft.hard_max_salary_usd}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_max_salary_usd: value,
                        })
                      }
                    />
                  </div>

                  <label
                    className="flex items-center gap-2 text-xs font-semibold cursor-pointer select-none"
                    style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  >
                    <input
                      type="checkbox"
                      checked={filtersGuidedDraft.hard_require_remote}
                      onChange={(event) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          hard_require_remote: event.target.checked,
                        })
                      }
                    />
                    Require Remote — only keep jobs flagged as remote or hybrid
                  </label>
                </div>

                {/* Soft Filters */}
                <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
                  <h4
                    className="text-sm font-bold uppercase tracking-wide"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    Soft Filters
                  </h4>
                  <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                    Soft filters auto-categorize jobs without running the gate agent.
                  </p>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <LabeledTextarea
                      label={`Negative Keywords — auto-FILTER (${countListItems(filtersGuidedDraft.soft_negative_keywords)} entries) — one per line`}
                      value={filtersGuidedDraft.soft_negative_keywords}
                      rows={5}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          soft_negative_keywords: value,
                        })
                      }
                    />
                    <LabeledTextarea
                      label={`Positive Keywords — auto-QUALIFY (${countListItems(filtersGuidedDraft.soft_positive_keywords)} entries) — all must match`}
                      value={filtersGuidedDraft.soft_positive_keywords}
                      rows={5}
                      onChange={(value) =>
                        updateFiltersGuidedDraft({
                          ...filtersGuidedDraft,
                          soft_positive_keywords: value,
                        })
                      }
                    />
                  </div>

                  <LabeledInput
                    label="Max Experience Years (0 = disabled) — auto-FILTER if description mentions more than this"
                    value={filtersGuidedDraft.soft_max_experience_years}
                    onChange={(value) =>
                      updateFiltersGuidedDraft({
                        ...filtersGuidedDraft,
                        soft_max_experience_years: value,
                      })
                    }
                  />
                </div>

                <div className="flex justify-end">
                  <button
                    className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                    onClick={handleFiltersGuidedSave}
                    disabled={filtersYamlMutation.isPending || !isFiltersGuidedDirty}
                  >
                    {filtersYamlMutation.isPending ? "Saving..." : "Save Filters"}
                  </button>
                </div>
                {filtersQuery.isLoading && (
                  <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
                    Loading filters configuration...
                  </p>
                )}
                {filtersQuery.isError && (
                  <InlineErrorText message="Failed to load filters configuration." />
                )}
                {filtersYamlMutation.isError && (
                  <InlineErrorText
                    message={`Save failed: ${getErrorMessage(filtersYamlMutation.error)}`}
                  />
                )}
              </div>
            )}

            {activeFiltersTab === "filters" && (
              <div className="space-y-4">
                <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                  Advanced: edit `filters.yaml` directly.
                </p>
                <YamlEditor
                  modelPath="filters.yaml"
                  value={filtersYamlDraft}
                  onChange={(nextValue) => {
                    setFiltersYamlDraft(nextValue);
                    setIsFiltersDirty(true);
                  }}
                />
                <div className="flex justify-end">
                  <button
                    className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                    onClick={() => {
                      filtersYamlMutation.mutate(filtersYamlDraft);
                    }}
                    disabled={filtersYamlMutation.isPending || !isFiltersDirty}
                  >
                    {filtersYamlMutation.isPending ? "Saving..." : "Save Filters"}
                  </button>
                </div>
                {filtersQuery.isLoading && (
                  <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
                    Loading filters configuration...
                  </p>
                )}
                {filtersQuery.isError && (
                  <InlineErrorText message="Failed to load filters configuration." />
                )}
                {filtersYamlMutation.isError && (
                  <InlineErrorText
                    message={`Save failed: ${getErrorMessage(filtersYamlMutation.error)}`}
                  />
                )}
              </div>
            )}

            {activeFiltersTab === "sources" && (
              <div className="space-y-4">
                <div
                  className="rounded-xl border px-4 py-3 text-sm"
                  style={{
                    borderColor: COLOR_WARNING,
                    color: COLOR_ON_WARNING_CONTAINER,
                    backgroundColor: COLOR_WARNING_CONTAINER,
                  }}
                >
                  Danger Zone: aggressive LinkedIn/source settings may cause rate limiting or IP
                  blocks.
                </div>
                <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
                  Advanced: edit `companies.yaml` directly.
                </p>
                <YamlEditor
                  modelPath="companies.yaml"
                  value={sourcesYamlDraft}
                  onChange={(nextValue) => {
                    setSourcesYamlDraft(nextValue);
                    setIsSourcesDirty(true);
                  }}
                />
                <div className="flex justify-end">
                  <button
                    className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                    onClick={() => {
                      sourcesYamlMutation.mutate(sourcesYamlDraft);
                    }}
                    disabled={sourcesYamlMutation.isPending || !isSourcesDirty}
                  >
                    {sourcesYamlMutation.isPending ? "Saving..." : "Save Sources"}
                  </button>
                </div>
                {sourcesQuery.isLoading && (
                  <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
                    Loading sources configuration...
                  </p>
                )}
                {sourcesQuery.isError && (
                  <InlineErrorText message="Failed to load sources configuration." />
                )}
                {sourcesYamlMutation.isError && (
                  <InlineErrorText
                    message={`Save failed: ${getErrorMessage(sourcesYamlMutation.error)}`}
                  />
                )}
              </div>
            )}
          </section>
        </>
      )}

      {hasAnyError && (
        <div
          className="rounded-xl border px-4 py-3 text-sm"
          style={{
            borderColor: COLOR_ERROR,
            color: COLOR_ON_ERROR_CONTAINER,
            backgroundColor: COLOR_ERROR_CONTAINER,
          }}
        >
          One or more settings actions failed. Inspect field values and retry.
        </div>
      )}

      <div
        className="rounded-xl border px-4 py-3 text-xs"
        style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66`, color: COLOR_ON_SURFACE_VARIANT }}
      >
        Legacy upload/download endpoints remain available for compatibility.
      </div>
    </div>
  );
}

/** Props for settings section tab buttons. */
interface TabButtonProps {
  /** Whether the tab is currently active. */
  readonly active: boolean;
  /** Tab label text. */
  readonly label: string;
  /** Click handler for tab activation. */
  readonly onClick: () => void;
}

/**
 * Render one compact settings tab button.
 *
 * @param props - Tab button props.
 * @returns One tab button element.
 */
function TabButton({ active, label, onClick }: TabButtonProps): JSX.Element {
  return (
    <button
      className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
        active ? "text-white" : "bg-white"
      }`}
      style={
        active
          ? { backgroundColor: COLOR_PRIMARY, borderColor: COLOR_PRIMARY }
          : { color: COLOR_ON_SURFACE_VARIANT, borderColor: COLOR_OUTLINE_VARIANT }
      }
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/** Props for labeled single-line input. */
interface LabeledInputProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one labeled text input.
 *
 * @param props - Labeled input props.
 * @returns One input field block.
 */
function LabeledInput({ label, value, onChange }: LabeledInputProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </label>
  );
}

/** Props for labeled select input. */
interface LabeledSelectProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
  /** Select options in display order. */
  readonly options: readonly SelectOption[];
  /** Optional helper text shown below select. */
  readonly helperText?: string;
}

/**
 * Render one labeled select input.
 *
 * @param props - Labeled select props.
 * @returns One select field block.
 */
function LabeledSelect({
  label,
  value,
  onChange,
  options,
  helperText,
}: LabeledSelectProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <select
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {options.map((option) => (
          <option key={`${label}-${option.value}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {helperText !== undefined && (
        <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
          {helperText}
        </p>
      )}
    </label>
  );
}

/** Props for labeled textarea input. */
interface LabeledTextareaProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
  /** Optional row count override. */
  readonly rows?: number;
  /** Optional helper text shown below textarea. */
  readonly helperText?: string;
}

/**
 * Render one labeled textarea.
 *
 * @param props - Labeled textarea props.
 * @returns One textarea block.
 */
function LabeledTextarea({
  label,
  value,
  onChange,
  rows = 5,
  helperText,
}: LabeledTextareaProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <textarea
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-2 text-sm"
        rows={rows}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {helperText !== undefined && (
        <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
          {helperText}
        </p>
      )}
    </label>
  );
}

/** Props for compact file metadata cards. */
interface SettingsFileCardProps {
  /** File card title. */
  readonly title: string;
  /** File metadata subtitle text. */
  readonly subtitle: string;
  /** Download URL for file action link. */
  readonly downloadUrl: string;
}

/**
 * Render one compact settings file metadata card.
 *
 * @param props - File card props.
 * @returns One file metadata card element.
 */
function SettingsFileCard({ title, subtitle, downloadUrl }: SettingsFileCardProps): JSX.Element {
  return (
    <div className="flex items-center justify-between rounded-xl border border-outline-variant bg-surface-container-low px-4 py-3">
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
          {subtitle}
        </p>
      </div>
      <a
        className="text-sm font-semibold hover:underline"
        href={downloadUrl}
        target="_blank"
        rel="noreferrer"
        style={{ color: COLOR_PRIMARY }}
      >
        Download
      </a>
    </div>
  );
}

/** Props for monaco-backed YAML editor wrapper. */
interface YamlEditorProps {
  /** Model URI path for schema matching. */
  readonly modelPath: string;
  /** Current editor value. */
  readonly value: string;
  /** Callback invoked on editor value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one Monaco YAML editor with schema tooling enabled.
 *
 * @param props - YAML editor props.
 * @returns One editor panel element.
 */
function YamlEditor({ modelPath, value, onChange }: YamlEditorProps): JSX.Element {
  function handleBeforeMount(monaco: Monaco): void {
    configureYamlSchemas(monaco);
  }

  return (
    <div className="overflow-hidden rounded-xl border border-outline-variant">
      <Editor
        beforeMount={handleBeforeMount}
        path={modelPath}
        defaultLanguage="yaml"
        height={`${EDITOR_HEIGHT_PX}px`}
        value={value}
        onChange={(nextValue) => {
          onChange(nextValue ?? "");
        }}
        options={{
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          wordWrap: "on",
          automaticLayout: true,
        }}
      />
    </div>
  );
}

/** Props for inline settings error text snippets. */
interface InlineErrorTextProps {
  /** Error text content. */
  readonly message: string;
}

/**
 * Render one compact inline error message.
 *
 * @param props - Error message props.
 * @returns One styled error paragraph.
 */
function InlineErrorText({ message }: InlineErrorTextProps): JSX.Element {
  return (
    <p className="text-sm" style={{ color: COLOR_ERROR }}>
      {message}
    </p>
  );
}
