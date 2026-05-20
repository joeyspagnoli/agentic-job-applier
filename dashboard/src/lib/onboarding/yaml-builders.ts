/**
 * @packageDocumentation
 *
 * Pure helpers that turn onboarding draft slices into YAML strings.
 *
 * @remarks
 * Every function in this module is pure — no fetch, no DOM, no React. The
 * helpers cover three concerns:
 *
 * - escaping user input safely into YAML scalars and mapping keys;
 * - deriving title/domain regexes from the candidate's free-form target
 *   roles;
 * - assembling the `filters.yaml` and `github_repos:` blocks consumed by
 *   the backend.
 */

import {
  HARDWARE_ROLE_KEYWORDS,
  PM_ROLE_KEYWORDS,
  QUANT_ROLE_KEYWORDS,
  SOFTWARE_ROLE_KEYWORDS,
} from "./role-keywords";
import { deriveRequireTitlePatterns, extractDomainKeywords } from "./title-patterns";
import type { FiltersDraft, RolesDraft } from "./types";

// Re-export so older imports continue to work via this module path.
export {
  HARDWARE_ROLE_KEYWORDS,
  PM_ROLE_KEYWORDS,
  QUANT_ROLE_KEYWORDS,
  SOFTWARE_ROLE_KEYWORDS,
  deriveRequireTitlePatterns,
  extractDomainKeywords,
};

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
export function escapeYamlDoubleQuoted(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

/**
 * Wrap a value in a double-quoted YAML scalar with all unsafe characters escaped.
 *
 * @param value - The raw value to embed.
 * @returns A complete YAML scalar token (including the surrounding quotes).
 */
export function toYamlDoubleQuoted(value: string): string {
  return `"${escapeYamlDoubleQuoted(value)}"`;
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
export function escapeYamlMappingKey(name: string): string {
  const isPlainKeySafe = /^[A-Za-z0-9][A-Za-z0-9 .&()_-]*$/.test(name);
  if (isPlainKeySafe) {
    return name;
  }
  return toYamlDoubleQuoted(name);
}

/**
 * Split multiline text into a trimmed string array, filtering out blanks.
 *
 * @param text - Raw multiline text.
 * @returns Array of non-empty trimmed lines.
 */
export function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
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
 * that the GitHubRepoFetcher receives `null` (no filter) and returns
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
/**
 * Flip the `enabled` flag inside an existing top-level `adzuna:` block.
 *
 * @remarks
 * Surgical edit: leaves comments, sibling fields, and adjacent blocks
 * intact. When the file does not yet contain an `adzuna:` block, a
 * minimal one is appended at the end of the document so older user
 * configs (created before issue #9) still pick up the toggle.
 *
 * @param yamlText - Full text of `companies.yaml`.
 * @param enabled - New value for `adzuna.enabled`.
 * @returns Updated YAML text with the flag set to {@link enabled}.
 */
export function setAdzunaEnabledInYaml(yamlText: string, enabled: boolean): string {
  const enabledLine = `  enabled: ${enabled ? "true" : "false"}`;
  const blockHeader = /^adzuna:\s*$/m;
  if (!blockHeader.test(yamlText)) {
    const trailingNewline = yamlText.endsWith("\n") ? "" : "\n";
    return (
      yamlText +
      trailingNewline +
      `\nadzuna:\n${enabledLine}\n  country: "us"\n  results_wanted: 50\n`
    );
  }
  const lines = yamlText.split("\n");
  let inBlock = false;
  let updated = false;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (/^adzuna:\s*$/.test(line)) {
      inBlock = true;
      continue;
    }
    if (inBlock) {
      // A non-indented, non-blank, non-comment line ends the block.
      if (line !== "" && !/^\s/.test(line) && !line.startsWith("#")) {
        break;
      }
      if (/^\s+enabled:\s*(true|false)\s*$/.test(line)) {
        lines[i] = enabledLine;
        updated = true;
        break;
      }
    }
  }
  if (!updated) {
    // Block exists but no enabled key — splice one in immediately after header.
    const headerIdx = lines.findIndex((line) => /^adzuna:\s*$/.test(line));
    if (headerIdx >= 0) {
      lines.splice(headerIdx + 1, 0, enabledLine);
    }
  }
  return lines.join("\n");
}

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
 * Build YAML for the keyless aggregator sources — JobSpy boards (Indeed,
 * LinkedIn, Glassdoor) and the direct LinkedIn scraper — so new users get
 * jobs from these the moment onboarding finishes.
 *
 * @remarks
 * These sources do not require an API key (JobSpy scrapes the public boards
 * and the LinkedIn scraper uses the same public guest API). Before this
 * helper existed, a fresh wizard run only seeded the SimplifyJobs github
 * source, so users saw a single source unless they hand-edited
 * `companies.yaml`. The defaults here mirror what discovery runs accept and
 * are safe to leave on: `results_wanted` is small so the first cycle is
 * fast, and location defaults to nationwide US which matches the broadest
 * intern audience.
 *
 * @param searchTerms - Free-form search terms from the wizard (e.g.
 *   `["software engineer intern", "ai engineer intern"]`). When empty,
 *   the builder falls back to a single generic term so each board still
 *   issues at least one query.
 * @returns Two YAML fragments concatenated by a blank line: the
 *   `job_boards:` mapping (Indeed/LinkedIn/Glassdoor under JobSpy) and the
 *   top-level `linkedin:` direct-scraper block.
 */
export function buildKeylessBoardsBlocks(searchTerms: string[]): string {
  const terms =
    searchTerms.length > 0 ? searchTerms : ["software engineer intern"];
  const termLines = terms.map((t) => `      - "${t.replace(/"/g, '\\"')}"`).join("\n");
  const jobBoards =
    `job_boards:\n` +
    `  indeed:\n` +
    `    enabled: true\n` +
    `    search_terms:\n${termLines}\n` +
    `    location: "United States"\n` +
    `    results_wanted: 25\n` +
    `  linkedin:\n` +
    `    enabled: true\n` +
    `    search_terms:\n${termLines}\n` +
    `    location: "United States"\n` +
    `    results_wanted: 25\n` +
    `  glassdoor:\n` +
    `    enabled: true\n` +
    `    search_terms:\n${termLines}\n` +
    `    location: "United States"\n` +
    `    results_wanted: 25\n`;
  const linkedinScraper =
    `linkedin:\n` +
    `  enabled: true\n` +
    `  search_terms:\n${termLines}\n` +
    `  location: "United States"\n` +
    `  geo_id: 103644278\n`;
  return jobBoards + "\n" + linkedinScraper;
}
