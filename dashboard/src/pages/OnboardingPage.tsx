/**
 * @packageDocumentation
 *
 * Multi-step onboarding wizard for first-time AutoApply setup.
 *
 * @remarks
 * Guides the user through profile creation, target roles, resume upload,
 * hard filters, AI provider configuration, and optional company watchlist.
 * Skippable steps are marked; the wizard persists progress server-side.
 */

import type { JSX, ChangeEvent } from "react";
import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  updateProfileStructured,
  updateAiProviderSettings,
  startCodexAuth,
  fetchCodexAuthStatus,
  uploadResume,
  uploadResumePdf,
  updateFiltersYaml,
  fetchSourcesSettings,
  updateSourcesYaml,
} from "@/lib/api/client";
import type { AiProviderMode, AiProviderType } from "@/lib/api/client";
import {
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_ERROR,
  COLOR_SUCCESS,
  COLOR_WARNING,
} from "@/lib/design-tokens";
import knownSlugsData from "../data/greenhouse_known_slugs.json";

/** Lookup table of known Greenhouse slugs, populated from the bundled JSON fixture. */
const KNOWN_SLUGS: Record<string, string | null> = knownSlugsData.companies as Record<
  string,
  string | null
>;

/** Total number of wizard steps. */
const STEP_COUNT = 6;

/**
 * How long the onboarding wizard keeps the watchlist warning on screen
 * before redirecting to the dashboard.
 *
 * @remarks
 * Long enough that a user can read 1–2 sentences of warning copy without
 * feeling rushed; short enough that a user who saw all-clear before the
 * warning was rendered is not stuck staring at a "Redirecting…" message.
 */
const WATCHLIST_WARNING_REDIRECT_DELAY_MS = 3500;

/** Step labels shown in the progress indicator. */
const STEP_LABELS = [
  "About You",
  "Target Roles",
  "Resume",
  "Filters",
  "AI Provider",
  "Watchlist",
] as const;

/**
 * Keywords in target role strings that indicate a hardware or electrical engineering domain.
 *
 * @remarks
 * SimplifyJobs uses `"Hardware"` as the category label. We detect it from role
 * titles because EE/hardware students phrase roles very differently from software
 * students but need the same GitHub source to return results.
 */
const HARDWARE_ROLE_KEYWORDS = [
  "electrical",
  "hardware",
  "embedded",
  "fpga",
  "rf",
  "vlsi",
  "ece",
  "circuit",
  "pcb",
  "firmware",
] as const;

/** Keywords in target role strings that indicate a software engineering domain. */
const SOFTWARE_ROLE_KEYWORDS = [
  "software",
  "swe",
  "frontend",
  "backend",
  "fullstack",
  "full-stack",
  "web developer",
  "mobile",
  "ios developer",
  "android",
] as const;

/** Keywords in target role strings that indicate a product management domain. */
const PM_ROLE_KEYWORDS = ["product manager", "product management", "program manager"] as const;

/** Keywords in target role strings that indicate a quantitative finance domain. */
const QUANT_ROLE_KEYWORDS = ["quant", "quantitative"] as const;

/** Draft state for step 1: basic profile info. */
interface ProfileDraft {
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

/** Draft state for step 5: AI provider. */
interface ProviderDraft {
  mode: AiProviderMode;
  providerType: AiProviderType;
  apiKey: string;
  codexStatus: "idle" | "starting" | "running" | "completed" | "failed";
  codexUrl: string | null;
  codexCode: string | null;
}

/** Draft state for step 6: company watchlist. */
interface WatchlistDraft {
  companies: string;
}

/**
 * Build the default empty profile draft.
 *
 * @returns Fresh profile draft with empty fields.
 */
function defaultProfileDraft(): ProfileDraft {
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
function defaultRolesDraft(): RolesDraft {
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
function defaultFiltersDraft(): FiltersDraft {
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
function defaultProviderDraft(): ProviderDraft {
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
 * Escape a string so it is safe to embed inside a YAML double-quoted scalar.
 *
 * @remarks
 * YAML double-quoted scalars treat `\` as an escape introducer and `"` as the
 * scalar terminator. Both characters must be backslash-escaped before
 * interpolation, otherwise a value like `Acme "Quoted" Co` would emit
 * `"Acme "Quoted" Co"` and break the YAML parser. See
 * https://yaml.org/spec/1.2.2/#73-flow-scalar-styles for the full grammar.
 *
 * @param value - The raw user-supplied string to escape.
 * @returns The escaped string, ready to be wrapped in `"..."`.
 */
function escapeYamlDoubleQuoted(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

/**
 * Wrap a value in a double-quoted YAML scalar with all unsafe characters escaped.
 *
 * @param value - The raw value to embed.
 * @returns A complete YAML scalar token (including the surrounding quotes).
 */
function toYamlDoubleQuoted(value: string): string {
  return `"${escapeYamlDoubleQuoted(value)}"`;
}

/**
 * Generic vocabulary that carries no domain signal — entry-level cues, role-
 * suffix nouns, structural articles, semester names, and degree levels.
 *
 * @remarks
 * Used by {@link extractDomainKeywords} to strip non-discriminating words
 * from the candidate's target roles before deriving title patterns. Anything
 * left over after this filter is treated as the candidate's domain
 * vocabulary (e.g., "fpga", "hardware", "circuit").
 */
const TITLE_KEYWORD_STOPWORDS: ReadonlySet<string> = new Set([
  "intern",
  "internship",
  "interns",
  "interns'",
  "coop",
  "co-op",
  "new",
  "grad",
  "grads",
  "graduate",
  "junior",
  "jr",
  "entry",
  "level",
  "early",
  "career",
  "rotational",
  "engineer",
  "engineers",
  "engineering",
  "developer",
  "developers",
  "scientist",
  "scientists",
  "specialist",
  "specialists",
  "technician",
  "technicians",
  "analyst",
  "analysts",
  "associate",
  "associates",
  "assistant",
  "assistants",
  "design",
  "designer",
  "designers",
  "the",
  "a",
  "an",
  "and",
  "or",
  "of",
  "in",
  "at",
  "for",
  "to",
  "with",
  "on",
  "summer",
  "fall",
  "spring",
  "winter",
  "season",
  "year",
  "round",
  "bachelor",
  "bachelors",
  "master",
  "masters",
  "phd",
  "mba",
]);

/**
 * Maximum character distance allowed between an entry-level signal and a
 * domain keyword in a job title. Generous enough to span "Internship: UWB
 * Validation Test Management Automotive UWB" but tight enough that the two
 * tokens really do refer to the same role.
 */
const TITLE_PATTERN_MAX_GAP = 80;

/**
 * Tokenize candidate target roles and return discriminating domain keywords.
 *
 * @remarks
 * Splits on whitespace and common punctuation, lower-cases each token, and
 * drops tokens that appear in {@link TITLE_KEYWORD_STOPWORDS}. The remaining
 * tokens (e.g., "fpga", "embedded", "circuit") form the domain vocabulary
 * used to require role-relevance in the title filter.
 *
 * @param targetRolesText - Raw multi-line target roles text from the wizard.
 * @returns De-duplicated lower-case domain keywords; empty when the user
 *   only listed generic role nouns.
 */
export function extractDomainKeywords(targetRolesText: string): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const raw of targetRolesText.toLowerCase().split(/[\s/\-,()]+/)) {
    const cleaned = raw.replace(/[^a-z0-9]/g, "");
    if (cleaned.length < 3) continue;
    if (TITLE_KEYWORD_STOPWORDS.has(cleaned)) continue;
    if (seen.has(cleaned)) continue;
    seen.add(cleaned);
    ordered.push(cleaned);
  }
  return ordered;
}

/**
 * Derive `hard_filters.require_title_patterns` from the candidate's target roles.
 *
 * @remarks
 * The pre-gate filter has to do role-relevance triage on its own: discovery
 * fetches every "Intern" title across 90+ ATS tenants, and the LLM gate
 * worker may not be running yet (no API key on first install). A naive
 * `\bintern\b` requirement lets through Nursing, Pharmacy, IT-Billing,
 * Marketing, and Accounting interns — none of which an electrical-
 * engineering candidate cares about.
 *
 * To gate properly we require **both** an entry-level signal AND a domain
 * keyword extracted from the candidate's own target roles, in either
 * order, within {@link TITLE_PATTERN_MAX_GAP} characters. The output is
 * two regex patterns (one per ordering) which the JobFilter ORs together —
 * net effect: titles must contain a domain keyword AND an intern/co-op/
 * new-grad term. "Nursing Intern" is rejected; "Electrical Engineering
 * Intern" passes; "Hardware Engineer Intern" passes; "Internship: UWB
 * Validation" with "uwb" or "validation" in target_roles passes.
 *
 * Fallback: when no entry-level signal is detected (candidate targeting
 * senior roles), no patterns are emitted and all titles pass through. When
 * entry-level signals exist but no domain keywords could be extracted
 * (target_roles say only "Intern"), we fall back to the broad intern-only
 * pattern — better than rejecting everything.
 *
 * @param targetRolesText - Raw multi-line target roles text from the wizard.
 * @returns Regex patterns to populate `hard_filters.require_title_patterns`.
 */
export function deriveRequireTitlePatterns(targetRolesText: string): string[] {
  const lowered = targetRolesText.toLowerCase();
  const internAlts: string[] = [];
  if (/\bintern(ship)?\b/.test(lowered)) internAlts.push("intern(ship)?");
  if (/\bco-?op\b/.test(lowered)) internAlts.push("co-?op");
  if (/\bnew\s+grad(uate)?\b/.test(lowered)) internAlts.push("new\\s+grad(uate)?");
  if (/\bearly\s+career\b/.test(lowered)) internAlts.push("early\\s+career");
  if (/\b(junior|jr\.?|entry[\s-]level)\b/.test(lowered)) {
    internAlts.push("junior", "jr\\.?", "entry[\\s-]level");
  }

  if (internAlts.length === 0) return [];

  const internPart = `\\b(?:${internAlts.join("|")})\\b`;
  const domainKeywords = extractDomainKeywords(targetRolesText);

  if (domainKeywords.length === 0) {
    // No discriminating domain words — keep the broad intern-only filter so
    // the candidate at least gets entry-level results.
    return [`(?i)${internPart}`];
  }

  const domainPart = `\\b(?:${domainKeywords.join("|")})\\b`;
  return [
    `(?i)${domainPart}.{0,${TITLE_PATTERN_MAX_GAP}}${internPart}`,
    `(?i)${internPart}.{0,${TITLE_PATTERN_MAX_GAP}}${domainPart}`,
  ];
}

/**
 * Serialize the onboarding filters draft and domain keywords to a filters.yaml string.
 *
 * @remarks
 * Writes both `hard_filters` (title/company/salary exclusions) and `soft_filters`
 * (domain-specific auto-qualification and generic negative signals). The
 * `positive_keywords` under `soft_filters` come from the user's `strongestAreas`
 * so that jobs mentioning any of those skills are auto-qualified without needing
 * the gate agent. The `require_title_patterns` come from {@link deriveRequireTitlePatterns}
 * so role-irrelevant postings (e.g., senior or director-level jobs for an intern
 * candidate) are rejected before they enter the database. All user-supplied
 * strings pass through {@link escapeYamlDoubleQuoted} so that quote and backslash
 * characters in company names or title patterns cannot produce malformed YAML.
 *
 * @param draft - The filters draft state from the onboarding wizard.
 * @param roles - The roles draft; `strongestAreas` becomes `soft_filters.positive_keywords`
 *   and `targetRoles` drives `hard_filters.require_title_patterns`.
 * @returns YAML string ready to write to filters.yaml.
 */
export function buildFiltersYaml(draft: FiltersDraft, roles: RolesDraft): string {
  const minSalary = parseInt(draft.minSalary, 10) || 0;
  const maxSalary = parseInt(draft.maxSalary, 10) || 0;
  const excludeTitles = draft.excludeTitlePatterns
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((pattern) => `(?i)${pattern}`);
  const excludeCompanies = draft.excludeCompanies
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const domainKeywords = splitLines(roles.strongestAreas);
  const requireTitlePatterns = deriveRequireTitlePatterns(roles.targetRoles);

  const lines: string[] = [
    "hard_filters:",
    `  min_salary_usd: ${minSalary}`,
    `  max_salary_usd: ${maxSalary}`,
    `  require_remote: ${draft.requireRemote}`,
    "  exclude_companies:",
    ...excludeCompanies.map((company) => `    - ${toYamlDoubleQuoted(company)}`),
    "  exclude_title_patterns:",
    ...excludeTitles.map((pattern) => `    - ${toYamlDoubleQuoted(pattern)}`),
    "  exclude_job_types: []",
    requireTitlePatterns.length === 0
      ? "  require_title_patterns: []"
      : "  require_title_patterns:",
    ...requireTitlePatterns.map((pattern) => `    - ${toYamlDoubleQuoted(pattern)}`),
    "  exclude_locations: []",
    "  max_days_old: 30",
    "soft_filters:",
    "  positive_keywords:",
    ...domainKeywords.map((keyword) => `    - ${toYamlDoubleQuoted(keyword)}`),
    "  negative_keywords:",
    '    - "clearance required"',
    '    - "security clearance"',
    '    - "5+ years"',
    '    - "7+ years"',
    '    - "help desk"',
    '    - "it support"',
  ];
  return lines.join("\n");
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
 * Probe a guessed Greenhouse board slug against the public boards API.
 *
 * @remarks
 * Hits the public `/departments` endpoint which is unauthenticated and
 * CORS-safe. A 2xx response means the board exists; any other HTTP status
 * is treated as `not_found` (Greenhouse uses 404 in practice). Any thrown
 * error from `fetch` — DNS failure, CORS denial, offline browser — yields
 * `network_error` so the caller can distinguish "user typo" from
 * "we could not reach Greenhouse".
 *
 * @param slug - The guessed Greenhouse board identifier (lowercase, no spaces).
 * @returns The classified outcome of the probe.
 */
export async function validateGreenhouseSlug(slug: string): Promise<GreenhouseSlugStatus> {
  try {
    const response = await fetch(
      `https://boards-api.greenhouse.io/v1/boards/${encodeURIComponent(slug)}/departments`,
    );
    if (response.ok) {
      return "verified";
    }
    return "not_found";
  } catch {
    return "network_error";
  }
}

/**
 * Resolve a company name to a Greenhouse slug using a two-layer strategy.
 *
 * @remarks
 * Layer 1: case-insensitive exact lookup in the bundled JSON fixture. A
 * `null` entry means the company is confirmed absent from Greenhouse (it
 * uses Workday, Taleo, SAP SuccessFactors, etc.) and no API call is made.
 * A string entry is the verified slug — returned immediately.
 *
 * Layer 2: sequential multi-pattern fallback for companies not in the
 * fixture. Tries up to four slug transforms and stops on the first 200.
 * Returns `not_found` when all patterns fail with 404, or `network_error`
 * when every pattern hit a network-layer failure before any 404 was seen.
 *
 * @param name - The user-facing company name from the watchlist textarea.
 * @param knownSlugs - Lookup table mapping company names to known slugs.
 *   `null` means confirmed not on Greenhouse; a string is the verified slug;
 *   a missing key means unknown (fall through to Layer 2).
 * @returns The resolved slug (empty string for `not_on_greenhouse`) and the
 *   resolution status.
 */
export async function resolveGreenhouseSlug(
  name: string,
  knownSlugs: Record<string, string | null>,
): Promise<{ slug: string; status: GreenhouseSlugStatus }> {
  const key = Object.keys(knownSlugs).find((k) => k.toLowerCase() === name.toLowerCase());
  if (key !== undefined) {
    const val = knownSlugs[key];
    if (val === null) return { slug: "", status: "not_on_greenhouse" };
    return { slug: val, status: "verified" };
  }

  const base = name.toLowerCase();
  const patterns = [
    base.replace(/\s+/g, ""),
    base.replace(/\s+/g, "-"),
    base.split(" ")[0] ?? base,
    base.replace(/\s+(inc|corp|llc|ltd|co)\.?\s*$/i, "").replace(/\s+/g, ""),
  ];

  let hadNetworkError = false;
  for (const slug of patterns) {
    const status = await validateGreenhouseSlug(slug);
    if (status === "verified") return { slug, status };
    if (status === "network_error") hadNetworkError = true;
  }
  return {
    slug: patterns[0] ?? base,
    status: hadNetworkError ? "network_error" : "not_found",
  };
}

/**
 * Outcome of {@link saveWatchlistCompanies}.
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

/** Empty result returned when there are no companies to save. */
const EMPTY_WATCHLIST_RESULT: WatchlistSaveResult = {
  unverified: [],
  networkFailures: [],
  notOnGreenhouse: [],
};

/**
 * Validate every guessed slug, then merge the watchlist into the
 * `greenhouse_companies` block of sources YAML.
 *
 * @remarks
 * Even when validation fails for every entry, the YAML is still written —
 * the user can fix the slug from Settings → Sources, but losing their
 * typed-in list silently would be the worse failure mode. All written
 * fields pass through {@link escapeYamlDoubleQuoted} so that company names
 * containing quotes do not corrupt the sources file.
 *
 * @param companiesText - Newline-separated company names from the watchlist step.
 * @param updateSources - API function to persist the merged sources YAML.
 * @param fetchSources - API function to read the current sources YAML.
 * @returns A {@link WatchlistSaveResult} partitioning companies into
 *   `unverified` (404 from Greenhouse) and `networkFailures` (no response).
 */
export async function saveWatchlistCompanies(
  companiesText: string,
  updateSources: (yaml: string) => Promise<unknown>,
  fetchSources: () => Promise<{ yaml_text: string }>,
): Promise<WatchlistSaveResult> {
  const companyNames = companiesText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (companyNames.length === 0) {
    return EMPTY_WATCHLIST_RESULT;
  }

  const validationResults = await Promise.allSettled(
    companyNames.map(async (name) => {
      const { slug, status } = await resolveGreenhouseSlug(name, KNOWN_SLUGS);
      return { name, slug, status };
    }),
  );

  const unverified: string[] = [];
  const networkFailures: string[] = [];
  const notOnGreenhouse: string[] = [];
  const newEntries: string[] = [];

  for (const result of validationResults) {
    if (result.status !== "fulfilled") {
      continue;
    }
    const { name, slug, status } = result.value;
    if (status === "not_on_greenhouse") {
      notOnGreenhouse.push(name);
      continue;
    }
    if (status === "not_found") unverified.push(name);
    else if (status === "network_error") networkFailures.push(name);
    newEntries.push(
      `  ${escapeYamlMappingKey(name)}:\n    greenhouse_id: ${toYamlDoubleQuoted(slug)}\n    priority: 3`,
    );
  }

  const replaceBlock =
    newEntries.length > 0
      ? `greenhouse_companies:\n${newEntries.join("\n")}\n`
      : `greenhouse_companies:\n`;
  const current = await fetchSources();
  let updatedYaml = current.yaml_text ?? "";
  if (/greenhouse_companies:/.test(updatedYaml)) {
    updatedYaml = updatedYaml.replace(/greenhouse_companies:\n(?:[ \t][^\n]*\n)*/, replaceBlock);
  } else {
    updatedYaml = updatedYaml + "\n" + replaceBlock;
  }
  await updateSources(updatedYaml);

  return { unverified, networkFailures, notOnGreenhouse };
}

/**
 * Build the user-facing warning messages for a {@link WatchlistSaveResult}.
 *
 * @remarks
 * Three failure modes produce distinct copy so the user knows what action
 * (if any) is required:
 * - `unverified`: slug was guessed wrong — fixable in Settings → Sources.
 * - `networkFailures`: Greenhouse was unreachable — retry later.
 * - `notOnGreenhouse`: company confirmed absent from Greenhouse — no YAML
 *   entry was written; user should add it to the career-page watcher instead.
 *
 * Returns two separate strings so the caller can render them as independent
 * dismissible banners.
 *
 * @param result - The outcome returned by {@link saveWatchlistCompanies}.
 * @returns `warning` for unverified/network failures, `notOnGreenhouseWarning`
 *   for confirmed-absent companies; either may be `null`.
 */
export function buildWatchlistWarning(result: WatchlistSaveResult): {
  warning: string | null;
  notOnGreenhouseWarning: string | null;
} {
  const sentences: string[] = [];
  if (result.unverified.length > 0) {
    sentences.push(
      `Could not verify Greenhouse IDs for: ${result.unverified.join(", ")}. Slugs were saved; correct them in Settings → Sources.`,
    );
  }
  if (result.networkFailures.length > 0) {
    sentences.push(
      `Could not reach Greenhouse to verify: ${result.networkFailures.join(", ")}. Slugs were saved as-is; re-verify from Settings → Sources once your connection is restored.`,
    );
  }
  const warning = sentences.length > 0 ? sentences.join(" ") : null;
  const notOnGreenhouseWarning =
    result.notOnGreenhouse.length > 0
      ? `${result.notOnGreenhouse.join(", ")} don't appear to use Greenhouse — they likely use a different ATS. No entries were added for them.`
      : null;
  return { warning, notOnGreenhouseWarning };
}

/**
 * Detect which SimplifyJobs categories apply to the user's target roles.
 *
 * @remarks
 * Performs a case-insensitive keyword scan across all role strings. When no
 * known keywords match (e.g. mechanical, civil, biomedical), an empty array is
 * returned so the caller omits the `categories:` field entirely, letting all
 * SimplifyJobs listings through rather than returning zero results.
 *
 * @param targetRoles - Role strings entered by the user (one per element).
 * @returns A subset of `["Software", "Hardware", "PM", "Quant"]` that matches
 *   the detected domain, or `[]` when the domain is unrecognised.
 *
 * @example
 * ```ts
 * detectSimplifyCategories(["Electrical Engineering Intern"]);
 * // → ["Hardware"]
 *
 * detectSimplifyCategories(["Software Engineering Intern", "ML Engineer"]);
 * // → ["Software"]
 *
 * detectSimplifyCategories(["Mechanical Engineering Intern"]);
 * // → []  (all categories pass through)
 * ```
 */
export function detectSimplifyCategories(targetRoles: string[]): string[] {
  const combined = targetRoles.join(" ").toLowerCase();
  const hasKeyword = (keywords: readonly string[]): boolean =>
    keywords.some((kw) => combined.includes(kw));

  const detected: string[] = [];
  if (hasKeyword(SOFTWARE_ROLE_KEYWORDS)) detected.push("Software");
  if (hasKeyword(HARDWARE_ROLE_KEYWORDS)) detected.push("Hardware");
  if (hasKeyword(PM_ROLE_KEYWORDS)) detected.push("PM");
  if (hasKeyword(QUANT_ROLE_KEYWORDS)) detected.push("Quant");
  return detected;
}

/**
 * Build the `github_repos:` YAML block for the SimplifyJobs internship source.
 *
 * @remarks
 * When `categories` is empty, the `categories:` field is omitted entirely so
 * that the {@link GitHubRepoFetcher} receives `null` (no filter) and returns
 * all listings. When `categories` is non-empty, only matching listings pass.
 *
 * @param categories - SimplifyJobs category strings to include, or `[]` for all.
 * @returns A YAML string fragment starting with `github_repos:\n`.
 *
 * @example
 * ```ts
 * buildGithubReposBlock([]);
 * // → "github_repos:\n  - owner: SimplifyJobs\n    ..."  (no categories line)
 *
 * buildGithubReposBlock(["Hardware"]);
 * // → "github_repos:\n  - owner: SimplifyJobs\n    ...\n    categories:\n      - \"Hardware\"\n"
 * ```
 */
export function buildGithubReposBlock(categories: string[]): string {
  const categoriesYaml =
    categories.length === 0
      ? ""
      : `    categories:\n${categories.map((c) => `      - "${c}"`).join("\n")}\n`;
  return (
    `github_repos:\n` +
    `  - owner: SimplifyJobs\n` +
    `    repo: Summer2026-Internships\n` +
    `    branch: dev\n` +
    `    json_path: .github/scripts/listings.json\n` +
    `    enabled: true\n` +
    categoriesYaml
  );
}

/**
 * Write the `github_repos` block into the sources YAML, replacing any
 * existing entry or appending when the key is absent.
 *
 * @remarks
 * Mirrors the fetch-replace-write pattern used by {@link saveWatchlistCompanies}.
 * Called during onboarding so every user gets the SimplifyJobs source
 * configured for their domain rather than the static `["Software"]` default
 * that shipped in the distribution template.
 *
 * The replacement regex matches both the inline form (`github_repos: []`) and
 * the multi-line block form, so re-running onboarding is idempotent.
 *
 * @param targetRoles - Role strings from the user's Target Roles step.
 * @param updateSources - API function to persist the merged sources YAML.
 * @param fetchSources - API function to read the current sources YAML.
 * @returns A promise that resolves once the updated YAML has been persisted.
 */
export async function seedGithubRepos(
  targetRoles: string[],
  updateSources: (yaml: string) => Promise<unknown>,
  fetchSources: () => Promise<{ yaml_text: string }>,
): Promise<void> {
  const categories = detectSimplifyCategories(targetRoles);
  const reposBlock = buildGithubReposBlock(categories);
  const current = await fetchSources();
  let updatedYaml = current.yaml_text ?? "";
  if (/github_repos:/.test(updatedYaml)) {
    updatedYaml = updatedYaml.replace(/github_repos:.*\n(?:[ \t][^\n]*\n)*/, reposBlock);
  } else {
    updatedYaml = updatedYaml + "\n" + reposBlock;
  }
  await updateSources(updatedYaml);
}

/**
 * Render a company name as a YAML mapping key safe for the
 * `greenhouse_companies` block.
 *
 * @remarks
 * Plain (unquoted) YAML keys may contain letters, digits, spaces, hyphens,
 * dots, ampersands, and parentheses without ambiguity. Anything outside
 * that set — colons, hashes, brackets, quotes — gets the full
 * double-quoted treatment so the file remains parseable.
 *
 * @param name - The display name typed by the user.
 * @returns The name formatted as a YAML mapping key.
 */
function escapeYamlMappingKey(name: string): string {
  const isPlainKeySafe = /^[A-Za-z0-9][A-Za-z0-9 .&()_-]*$/.test(name);
  if (isPlainKeySafe) {
    return name;
  }
  return toYamlDoubleQuoted(name);
}

/**
 * Multi-step onboarding wizard page component.
 *
 * @returns The onboarding wizard page content.
 */
export function OnboardingPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [profile, setProfile] = useState<ProfileDraft>(defaultProfileDraft);
  const [roles, setRoles] = useState<RolesDraft>(defaultRolesDraft);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState<boolean>(false);
  const [filters, setFilters] = useState<FiltersDraft>(defaultFiltersDraft);
  const [provider, setProvider] = useState<ProviderDraft>(defaultProviderDraft);
  const [watchlist, setWatchlist] = useState<WatchlistDraft>({ companies: "" });
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [notOnGreenhouseWarning, setNotOnGreenhouseWarning] = useState<string | null>(null);

  const resumeMutation = useMutation({
    mutationFn: (file: File) =>
      file.type === "application/pdf" ? uploadResumePdf(file) : uploadResume(file),
    onSuccess: () => {
      setResumeUploaded(true);
    },
  });

  const canAdvance = useCallback((): boolean => {
    if (currentStep === 0) {
      return profile.fullName.trim() !== "" && profile.email.trim() !== "";
    }
    if (currentStep === 1) {
      return roles.targetRoles.trim() !== "";
    }
    if (currentStep === 2) {
      return resumeUploaded;
    }
    return true;
  }, [currentStep, profile, roles, resumeUploaded]);

  /**
   * Advance to the next wizard step.
   *
   * @returns Nothing.
   */
  function handleNext(): void {
    if (currentStep < STEP_COUNT - 1) {
      setError(null);
      setCurrentStep(currentStep + 1);
    }
  }

  /**
   * Go back to the previous wizard step.
   *
   * @returns Nothing.
   */
  function handleBack(): void {
    if (currentStep > 0) {
      setError(null);
      setCurrentStep(currentStep - 1);
    }
  }

  /**
   * Submit all wizard data and redirect to dashboard.
   *
   * @returns Nothing.
   */
  async function handleFinish(): Promise<void> {
    setSaving(true);
    setError(null);
    setWarning(null);
    setNotOnGreenhouseWarning(null);

    try {
      await updateProfileStructured({
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
      });

      if (provider.mode === "byok" && provider.apiKey.trim() !== "") {
        await updateAiProviderSettings({
          mode: "byok",
          provider_type: provider.providerType,
          api_key: provider.apiKey,
        });
      }

      // Bug 5 fix: pass roles so strongestAreas populate soft_filters.positive_keywords
      const filtersYaml = buildFiltersYaml(filters, roles);
      await updateFiltersYaml(filtersYaml);

      await seedGithubRepos(splitLines(roles.targetRoles), updateSourcesYaml, fetchSourcesSettings);

      // Bug 4 fix: validate Greenhouse slugs; capture unverified + network
      // failures so each gets its own message in the UI below.
      const watchlistResult: WatchlistSaveResult =
        watchlist.companies.trim() !== ""
          ? await saveWatchlistCompanies(
              watchlist.companies,
              updateSourcesYaml,
              fetchSourcesSettings,
            )
          : EMPTY_WATCHLIST_RESULT;

      // Bug 2 fix: refetchQueries awaits the round-trip so OnboardingGate
      // reads is_complete: true before navigate("/") fires.
      await queryClient.refetchQueries({ queryKey: ["onboarding-status"] });

      const { warning: warningMessage, notOnGreenhouseWarning: notOnGreenhouseMessage } =
        buildWatchlistWarning(watchlistResult);
      if (warningMessage !== null) setWarning(warningMessage);
      if (notOnGreenhouseMessage !== null) setNotOnGreenhouseWarning(notOnGreenhouseMessage);
      if (warningMessage !== null || notOnGreenhouseMessage !== null) {
        window.setTimeout(() => {
          navigate("/");
        }, WATCHLIST_WARNING_REDIRECT_DELAY_MS);
      } else {
        navigate("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  /**
   * Initiate Codex device auth and poll for completion.
   *
   * @returns Nothing.
   */
  async function handleStartCodexAuth(): Promise<void> {
    setProvider((prev) => ({ ...prev, codexStatus: "starting" }));

    try {
      const snapshot = await startCodexAuth();
      setProvider((prev) => ({
        ...prev,
        codexStatus: snapshot.status === "running" ? "running" : "starting",
        codexUrl: snapshot.verification_url,
        codexCode: snapshot.device_code,
      }));

      pollCodexAuth();
    } catch {
      setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
    }
  }

  /**
   * Poll Codex auth status every 3 seconds until completed or failed.
   *
   * @returns Nothing.
   */
  function pollCodexAuth(): void {
    const intervalId = window.setInterval(async () => {
      try {
        const status = await fetchCodexAuthStatus();
        setProvider((prev) => ({
          ...prev,
          codexStatus: status.status,
          codexUrl: status.verification_url ?? prev.codexUrl,
          codexCode: status.device_code ?? prev.codexCode,
        }));

        if (status.status === "completed" || status.status === "failed") {
          window.clearInterval(intervalId);
        }
      } catch {
        window.clearInterval(intervalId);
        setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
      }
    }, 3000);
  }

  /**
   * Handle resume file selection.
   *
   * @param event - File input change event.
   * @returns Nothing.
   */
  function handleResumeFile(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0] ?? null;
    setResumeFile(file);
    if (file) {
      resumeMutation.mutate(file);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-8"
      style={{ backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}
    >
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="flex justify-center mb-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center signature-gradient">
              <span
                className="material-symbols-outlined text-white text-2xl"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                bolt
              </span>
            </div>
          </div>
          <h1
            className="text-fluid-2xl font-extrabold tracking-tight mb-2"
            style={{ color: COLOR_ON_SURFACE }}
          >
            Welcome to AutoApply
          </h1>
          <p className="text-fluid-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Let&apos;s set up your job search profile in a few quick steps.
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEP_LABELS.map((label, idx) => (
            <div key={label} className="flex items-center gap-2">
              <button
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200"
                style={{
                  backgroundColor:
                    idx === currentStep
                      ? COLOR_PRIMARY
                      : idx < currentStep
                        ? COLOR_PRIMARY_FIXED
                        : "transparent",
                  color:
                    idx === currentStep
                      ? "#ffffff"
                      : idx < currentStep
                        ? COLOR_PRIMARY
                        : COLOR_OUTLINE,
                }}
                onClick={() => {
                  if (idx <= currentStep) {
                    setCurrentStep(idx);
                  }
                }}
              >
                {idx < currentStep ? (
                  <span className="material-symbols-outlined text-[14px]">check</span>
                ) : (
                  <span className="text-[11px] font-bold">{idx + 1}</span>
                )}
                <span className="hidden sm:inline">{label}</span>
              </button>
              {idx < STEP_COUNT - 1 && (
                <div
                  className="w-6 h-px"
                  style={{
                    backgroundColor: idx < currentStep ? COLOR_PRIMARY : COLOR_OUTLINE_VARIANT,
                  }}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content card */}
        <div
          className="rounded-2xl p-8 ambient-shadow border"
          style={{
            backgroundColor: "#ffffff",
            borderColor: `${COLOR_OUTLINE_VARIANT}30`,
          }}
        >
          {currentStep === 0 && <StepProfile draft={profile} onChange={setProfile} />}
          {currentStep === 1 && <StepRoles draft={roles} onChange={setRoles} />}
          {currentStep === 2 && (
            <StepResume
              file={resumeFile}
              uploaded={resumeUploaded}
              uploading={resumeMutation.isPending}
              onFileChange={handleResumeFile}
            />
          )}
          {currentStep === 3 && <StepFilters draft={filters} onChange={setFilters} />}
          {currentStep === 4 && (
            <StepProvider
              draft={provider}
              onChange={setProvider}
              onStartCodex={() => {
                void handleStartCodexAuth();
              }}
            />
          )}
          {currentStep === 5 && <StepWatchlist draft={watchlist} onChange={setWatchlist} />}

          {error && (
            <p className="mt-4 text-sm font-medium" style={{ color: COLOR_ERROR }}>
              {error}
            </p>
          )}
          {warning && (
            <div
              className="mt-4 flex items-start gap-2 rounded-lg p-3 text-sm font-medium"
              style={{ backgroundColor: `${COLOR_WARNING}18`, color: COLOR_WARNING }}
            >
              <span className="flex-1">{warning}</span>
              <button
                onClick={() => setWarning(null)}
                aria-label="Dismiss"
                className="shrink-0 opacity-60 hover:opacity-100"
              >
                ✕
              </button>
            </div>
          )}
          {notOnGreenhouseWarning && (
            <div
              className="mt-2 flex items-start gap-2 rounded-lg p-3 text-sm font-medium"
              style={{ backgroundColor: `${COLOR_WARNING}18`, color: COLOR_WARNING }}
            >
              <span className="flex-1">{notOnGreenhouseWarning}</span>
              <button
                onClick={() => setNotOnGreenhouseWarning(null)}
                aria-label="Dismiss"
                className="shrink-0 opacity-60 hover:opacity-100"
              >
                ✕
              </button>
            </div>
          )}

          {/* Navigation buttons */}
          <div
            className="flex justify-between items-center mt-8 pt-6 border-t"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}30` }}
          >
            <button
              className="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
              style={{
                color: currentStep === 0 ? COLOR_OUTLINE : COLOR_ON_SURFACE_VARIANT,
                opacity: currentStep === 0 ? 0.4 : 1,
              }}
              disabled={currentStep === 0}
              onClick={handleBack}
            >
              Back
            </button>

            <div className="flex gap-3">
              {currentStep < STEP_COUNT - 1 && currentStep >= 2 && (
                <button
                  className="px-4 py-2 rounded-xl text-sm font-medium transition-colors"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  onClick={handleNext}
                >
                  Skip
                </button>
              )}
              {currentStep < STEP_COUNT - 1 ? (
                <button
                  className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
                  style={{ backgroundColor: COLOR_PRIMARY }}
                  disabled={!canAdvance()}
                  onClick={handleNext}
                >
                  Continue
                </button>
              ) : (
                <button
                  className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
                  style={{ backgroundColor: COLOR_PRIMARY }}
                  disabled={saving}
                  onClick={() => {
                    void handleFinish();
                  }}
                >
                  {saving ? "Saving..." : "Finish Setup"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step Components ────────────────────────────────────────────────

/** Props for an individual form input. */
interface FieldProps {
  /** Label text above the input. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Change callback. */
  readonly onChange: (value: string) => void;
  /** Input placeholder. */
  readonly placeholder?: string;
  /** Input type. */
  readonly type?: string;
  /** Whether to render a textarea instead. */
  readonly multiline?: boolean;
  /** Whether the field is required. */
  readonly required?: boolean;
}

/**
 * Reusable form field with label.
 *
 * @param props - {@link FieldProps}
 * @returns Labeled input element.
 */
function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  multiline,
  required,
}: FieldProps): JSX.Element {
  const inputClasses =
    "w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors focus:ring-2 focus:ring-primary/30";
  const inputStyle = {
    borderColor: COLOR_OUTLINE_VARIANT,
    color: COLOR_ON_SURFACE,
    backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
  };

  return (
    <label className="block">
      <span
        className="text-xs font-semibold mb-1.5 block"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
      >
        {label}
        {required && <span style={{ color: COLOR_ERROR }}> *</span>}
      </span>
      {multiline ? (
        <textarea
          className={inputClasses}
          style={inputStyle}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          placeholder={placeholder}
          rows={4}
        />
      ) : (
        <input
          className={inputClasses}
          style={inputStyle}
          type={type}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}

/**
 * Step 1: Basic profile information.
 *
 * @param props - Profile draft and change handler.
 * @returns Profile form fields.
 */
function StepProfile({
  draft,
  onChange,
}: {
  draft: ProfileDraft;
  onChange: (d: ProfileDraft) => void;
}): JSX.Element {
  /**
   * Update a single profile field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof ProfileDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          About You
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Basic contact information for your applications.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Full Name"
          value={draft.fullName}
          onChange={(v) => {
            set("fullName", v);
          }}
          placeholder="Jane Doe"
          required
        />
        <Field
          label="Email"
          value={draft.email}
          onChange={(v) => {
            set("email", v);
          }}
          placeholder="jane@example.com"
          type="email"
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Phone"
          value={draft.phone}
          onChange={(v) => {
            set("phone", v);
          }}
          placeholder="+1 555-0123"
        />
        <Field
          label="City"
          value={draft.city}
          onChange={(v) => {
            set("city", v);
          }}
          placeholder="San Francisco"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="State / Region"
          value={draft.stateOrRegion}
          onChange={(v) => {
            set("stateOrRegion", v);
          }}
          placeholder="California"
        />
        <Field
          label="Country Code"
          value={draft.countryCode}
          onChange={(v) => {
            set("countryCode", v);
          }}
          placeholder="US"
        />
      </div>
      <Field
        label="LinkedIn URL"
        value={draft.linkedinUrl}
        onChange={(v) => {
          set("linkedinUrl", v);
        }}
        placeholder="https://linkedin.com/in/..."
      />
      <Field
        label="Professional Summary"
        value={draft.summary}
        onChange={(v) => {
          set("summary", v);
        }}
        placeholder="Brief overview of your experience and goals..."
        multiline
      />
    </div>
  );
}

/**
 * Step 2: Target roles and search preferences.
 *
 * @param props - Roles draft and change handler.
 * @returns Roles form fields.
 */
function StepRoles({
  draft,
  onChange,
}: {
  draft: RolesDraft;
  onChange: (d: RolesDraft) => void;
}): JSX.Element {
  /**
   * Update a single roles field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof RolesDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Target Roles
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          What positions are you looking for? One per line.
        </p>
      </div>
      <Field
        label="Target Roles"
        value={draft.targetRoles}
        onChange={(v) => {
          set("targetRoles", v);
        }}
        placeholder="Software Engineer&#10;Full Stack Developer&#10;Backend Engineer"
        multiline
        required
      />
      <Field
        label="Strongest Areas"
        value={draft.strongestAreas}
        onChange={(v) => {
          set("strongestAreas", v);
        }}
        placeholder="Python&#10;React&#10;System Design"
        multiline
      />
      <Field
        label="Resume Tailor Notes"
        value={draft.experienceHighlights}
        onChange={(v) => {
          set("experienceHighlights", v);
        }}
        placeholder={
          "Led K8s migration reducing cold-start 8s → 800ms\nOwned on-call for 5M evals/day Python + K8s pipeline\nReact dashboard used by 200+ internal analysts\nStripe intern: fraud scoring 50K tx/day, PCI-DSS exposure"
        }
        multiline
      />
      <Field
        label="Job Board Search Terms"
        value={draft.searchTerms}
        onChange={(v) => {
          set("searchTerms", v);
        }}
        placeholder="software engineer&#10;full stack developer&#10;python developer"
        multiline
      />
    </div>
  );
}

/** Props for the resume step. */
interface StepResumeProps {
  /** Currently selected file, if any. */
  readonly file: File | null;
  /** Whether upload succeeded. */
  readonly uploaded: boolean;
  /** Whether upload is in progress. */
  readonly uploading: boolean;
  /** File input change handler. */
  readonly onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Step 3: Resume upload.
 *
 * @param props - {@link StepResumeProps}
 * @returns Resume upload form.
 */
function StepResume({ file, uploaded, uploading, onFileChange }: StepResumeProps): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Resume
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Upload your resume as a PDF, YAML, or .tex file. You can refine the structured content
          later in Settings.
        </p>
      </div>
      <div
        className="border-2 border-dashed rounded-2xl p-8 text-center transition-colors"
        style={{ borderColor: COLOR_OUTLINE_VARIANT }}
      >
        <span
          className="material-symbols-outlined text-4xl mb-3 block"
          style={{ color: COLOR_OUTLINE }}
        >
          upload_file
        </span>
        <p className="text-sm font-medium mb-4" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {file ? file.name : "Drag and drop or click to select"}
        </p>
        <label
          className="inline-block px-5 py-2 rounded-xl text-sm font-bold cursor-pointer transition-all scale-98-on-click"
          style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
        >
          Choose File
          <input
            type="file"
            accept=".yaml,.yml,.tex,.pdf"
            className="hidden"
            onChange={onFileChange}
          />
        </label>
        {uploading && (
          <p className="text-xs mt-3 animate-pulse" style={{ color: COLOR_PRIMARY }}>
            Uploading...
          </p>
        )}
        {uploaded && file?.type === "application/pdf" && (
          <p className="text-xs mt-3 font-semibold" style={{ color: COLOR_SUCCESS }}>
            PDF uploaded — visit Settings → Resume to add your work experience and skills.
          </p>
        )}
        {uploaded && file?.type !== "application/pdf" && (
          <p className="text-xs mt-3 font-semibold" style={{ color: COLOR_SUCCESS }}>
            Resume uploaded successfully
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Step 4: Hard filters for job search.
 *
 * @param props - Filters draft and change handler.
 * @returns Filters form fields.
 */
function StepFilters({
  draft,
  onChange,
}: {
  draft: FiltersDraft;
  onChange: (d: FiltersDraft) => void;
}): JSX.Element {
  /** All available job type options. */
  const jobTypeOptions = ["Full-time", "Part-time", "Contract", "Internship"];

  /**
   * Toggle a job type in the selected list.
   *
   * @param jt - Job type to toggle.
   */
  function toggleJobType(jt: string): void {
    const next = draft.jobTypes.includes(jt)
      ? draft.jobTypes.filter((t) => t !== jt)
      : [...draft.jobTypes, jt];
    onChange({ ...draft, jobTypes: next });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Filters
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Set hard filters to automatically exclude irrelevant jobs.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Min Salary (USD)"
          value={draft.minSalary}
          onChange={(v) => {
            onChange({ ...draft, minSalary: v });
          }}
          placeholder="80000"
          type="number"
        />
        <Field
          label="Max Salary (USD)"
          value={draft.maxSalary}
          onChange={(v) => {
            onChange({ ...draft, maxSalary: v });
          }}
          placeholder="200000"
          type="number"
        />
      </div>

      <div>
        <span
          className="text-xs font-semibold mb-2 block"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
        >
          Job Types
        </span>
        <div className="flex flex-wrap gap-2">
          {jobTypeOptions.map((jt) => (
            <button
              key={jt}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border"
              style={{
                backgroundColor: draft.jobTypes.includes(jt) ? COLOR_PRIMARY_FIXED : "transparent",
                color: draft.jobTypes.includes(jt) ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                borderColor: draft.jobTypes.includes(jt)
                  ? `${COLOR_PRIMARY}40`
                  : COLOR_OUTLINE_VARIANT,
              }}
              onClick={() => {
                toggleJobType(jt);
              }}
            >
              {jt}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={draft.requireRemote}
          onChange={(e) => {
            onChange({ ...draft, requireRemote: e.target.checked });
          }}
          className="w-4 h-4 rounded accent-primary"
        />
        <span className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
          Only show remote/hybrid positions
        </span>
      </label>

      <Field
        label="Exclude Title Patterns (one per line)"
        value={draft.excludeTitlePatterns}
        onChange={(v) => {
          onChange({ ...draft, excludeTitlePatterns: v });
        }}
        placeholder="intern&#10;junior&#10;director"
        multiline
      />
      <Field
        label="Exclude Companies (one per line)"
        value={draft.excludeCompanies}
        onChange={(v) => {
          onChange({ ...draft, excludeCompanies: v });
        }}
        placeholder="Acme Corp&#10;Initech"
        multiline
      />
    </div>
  );
}

/** Props for the AI provider step. */
interface StepProviderProps {
  /** Current provider draft state. */
  readonly draft: ProviderDraft;
  /** Draft change handler. */
  readonly onChange: (d: ProviderDraft) => void;
  /** Callback to initiate Codex device auth. */
  readonly onStartCodex: () => void;
}

/**
 * Step 5: AI provider configuration.
 *
 * @param props - {@link StepProviderProps}
 * @returns AI provider setup form.
 */
function StepProvider({ draft, onChange, onStartCodex }: StepProviderProps): JSX.Element {
  /** BYOK provider options. */
  const providers: { value: AiProviderType; label: string }[] = [
    { value: "openai", label: "OpenAI" },
    { value: "anthropic", label: "Anthropic" },
    { value: "gemini", label: "Google Gemini" },
    { value: "openrouter", label: "OpenRouter" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          AI Provider
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Choose how AutoApply accesses AI for resume tailoring and job scoring.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "codex" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "codex" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "codex" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => {
            onChange({ ...draft, mode: "codex" });
          }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">cloud</span>
          Codex (Subscription)
        </button>
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "byok" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "byok" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "byok" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => {
            onChange({ ...draft, mode: "byok" });
          }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">key</span>
          Bring Your Own Key
        </button>
      </div>

      {draft.mode === "codex" && (
        <div
          className="rounded-xl p-5 border"
          style={{
            borderColor: `${COLOR_OUTLINE_VARIANT}40`,
            backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
          }}
        >
          {draft.codexStatus === "idle" && (
            <>
              <p className="text-sm mb-3" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Sign in with your Codex/OpenAI subscription. A browser window will open for
                authentication.
              </p>
              <button
                className="px-5 py-2 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Sign in with Codex
              </button>
            </>
          )}
          {(draft.codexStatus === "starting" || draft.codexStatus === "running") && (
            <div className="space-y-3">
              <p className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
                Waiting for authentication...
              </p>
              {draft.codexUrl && (
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Open this URL and enter the code below:
                </p>
              )}
              {draft.codexUrl && (
                <a
                  href={draft.codexUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold underline"
                  style={{ color: COLOR_PRIMARY }}
                >
                  {draft.codexUrl}
                </a>
              )}
              {draft.codexCode && (
                <div
                  className="inline-block px-4 py-2 rounded-lg font-mono text-lg font-bold tracking-widest"
                  style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
                >
                  {draft.codexCode}
                </div>
              )}
              <p className="text-xs animate-pulse" style={{ color: COLOR_OUTLINE }}>
                Polling for completion...
              </p>
            </div>
          )}
          {draft.codexStatus === "completed" && (
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-lg" style={{ color: COLOR_SUCCESS }}>
                check_circle
              </span>
              <span className="text-sm font-semibold" style={{ color: COLOR_SUCCESS }}>
                Codex authentication complete
              </span>
            </div>
          )}
          {draft.codexStatus === "failed" && (
            <div className="space-y-2">
              <p className="text-sm font-medium" style={{ color: COLOR_ERROR }}>
                Authentication failed. Please try again.
              </p>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-white"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}

      {draft.mode === "byok" && (
        <div className="space-y-4">
          <div>
            <span
              className="text-xs font-semibold mb-2 block"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Provider
            </span>
            <div className="flex flex-wrap gap-2">
              {providers.map((p) => (
                <button
                  key={p.value}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all"
                  style={{
                    backgroundColor:
                      draft.providerType === p.value ? COLOR_PRIMARY_FIXED : "transparent",
                    color:
                      draft.providerType === p.value ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                    borderColor:
                      draft.providerType === p.value ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
                  }}
                  onClick={() => {
                    onChange({ ...draft, providerType: p.value });
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <Field
            label="API Key"
            value={draft.apiKey}
            onChange={(v) => {
              onChange({ ...draft, apiKey: v });
            }}
            placeholder="sk-..."
            type="password"
          />
        </div>
      )}
    </div>
  );
}

/**
 * Step 6: Optional company watchlist.
 *
 * @param props - Watchlist draft and change handler.
 * @returns Watchlist form.
 */
function StepWatchlist({
  draft,
  onChange,
}: {
  draft: WatchlistDraft;
  onChange: (d: WatchlistDraft) => void;
}): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Company Watchlist
          <span
            className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full"
            style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
          >
            Optional
          </span>
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Add specific companies to track. Their career pages will be scanned for new openings.
        </p>
      </div>
      <Field
        label="Companies (one per line)"
        value={draft.companies}
        onChange={(v) => {
          onChange({ ...draft, companies: v });
        }}
        placeholder="Stripe&#10;Notion&#10;Linear&#10;Vercel"
        multiline
      />
    </div>
  );
}

/**
 * Split multiline text into a trimmed string array, filtering out blanks.
 *
 * @param text - Raw multiline text.
 * @returns Array of non-empty trimmed lines.
 */
function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
