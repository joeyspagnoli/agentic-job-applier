/**
 * @packageDocumentation
 *
 * Greenhouse slug resolution and watchlist YAML persistence helpers.
 *
 * @remarks
 * The wizard collects company display names from the user, then needs to
 * convert each to a verified Greenhouse board slug before writing the
 * `greenhouse_companies` block of sources.yaml. This module owns:
 *
 * - probing the public Greenhouse boards API and classifying outcomes;
 * - the two-layer resolution strategy (lookup table → multi-pattern probe);
 * - merging the resolved slugs into existing sources YAML;
 * - rendering user-facing warning copy for each failure mode;
 * - seeding the SimplifyJobs `github_repos:` block based on detected role
 *   categories.
 */

import { KNOWN_SLUGS } from "./constants";
import { EMPTY_WATCHLIST_RESULT } from "./defaults";
import {
  buildGithubReposBlock,
  detectSimplifyCategories,
  escapeYamlMappingKey,
  toYamlDoubleQuoted,
} from "./yaml-builders";
import type { GreenhouseSlugStatus, WatchlistSaveResult } from "./types";

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
