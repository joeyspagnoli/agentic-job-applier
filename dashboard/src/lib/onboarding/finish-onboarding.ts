/**
 * @packageDocumentation
 *
 * Orchestrates the API calls fired when the user clicks "Finish Setup".
 *
 * @remarks
 * Pulled out of the page shell so the component file can stay under 300
 * lines. The fixed call order is load-bearing for the wizard's behaviour:
 *
 * 1. {@link FinishOnboardingArgs.updateProfileStructured} writes the user's
 *    contact info, target roles, and education before any source-config
 *    is touched. If this call fails, no destructive YAML rewrites have
 *    happened yet.
 * 2. BYOK API key is persisted only when present.
 * 3. `filters.yaml` is rewritten with the new domain-aware filter set.
 * 4. `sources.yaml` `github_repos:` block is seeded for the candidate's
 *    detected category (Software / Hardware / etc.).
 * 5. Watchlist companies are validated against Greenhouse and merged into
 *    the same `sources.yaml`.
 * 6. `onboarding-status` query is refetched (Bug 2 fix) so the
 *    `OnboardingGate` sees `is_complete: true` before the wizard navigates
 *    away — without this the user would bounce back to step 1.
 *
 * The function returns the watchlist save result so the caller can show
 * the dismissible warning banners; everything else is best-effort.
 */

import {
  updateAiProviderSettings,
  updateFiltersYaml,
  updateProfileStructured,
} from "@/lib/api/client";
import { EMPTY_WATCHLIST_RESULT } from "./defaults";
import { buildStructuredProfilePayload } from "./profile-payload";
import type {
  FiltersDraft,
  ProfileDraft,
  ProviderDraft,
  RolesDraft,
  WatchlistDraft,
  WatchlistSaveResult,
} from "./types";
import { buildFiltersYaml, splitLines } from "./yaml-builders";
import { saveWatchlistCompanies, seedGithubRepos } from "./watchlist";

/** Argument bundle for {@link finishOnboarding}. */
export interface FinishOnboardingArgs {
  readonly profile: ProfileDraft;
  readonly roles: RolesDraft;
  readonly filters: FiltersDraft;
  readonly provider: ProviderDraft;
  readonly watchlist: WatchlistDraft;
  /**
   * Sources-YAML reader; injected so the integration test can swap it
   * for a mock without monkey-patching the api/client module.
   */
  readonly fetchSources: () => Promise<{ yaml_text: string }>;
  /** Sources-YAML writer; same dependency-injection rationale as above. */
  readonly updateSources: (yaml: string) => Promise<unknown>;
  /**
   * `OnboardingGate` query refetch — must complete before the wizard
   * navigates away (Bug 2 fix).
   */
  readonly refetchOnboardingStatus: () => Promise<unknown>;
}

/**
 * Fire all wizard-completion API calls in the canonical order and return
 * the watchlist outcome.
 *
 * @param args - {@link FinishOnboardingArgs}
 * @returns The watchlist save result, used by the caller to render
 *   dismissible warning banners.
 */
export async function finishOnboarding(args: FinishOnboardingArgs): Promise<WatchlistSaveResult> {
  const {
    profile,
    roles,
    filters,
    provider,
    watchlist,
    fetchSources,
    updateSources,
    refetchOnboardingStatus,
  } = args;

  await updateProfileStructured(buildStructuredProfilePayload({ profile, roles, filters }));

  if (provider.mode === "byok" && provider.apiKey.trim() !== "") {
    await updateAiProviderSettings({
      mode: "byok",
      provider_type: provider.providerType,
      api_key: provider.apiKey,
    });
  }

  // Bug 5 fix: pass roles so strongestAreas populate soft_filters.positive_keywords.
  await updateFiltersYaml(buildFiltersYaml(filters, roles));

  await seedGithubRepos(splitLines(roles.targetRoles), updateSources, fetchSources);

  // Bug 4 fix: validate Greenhouse slugs; capture unverified + network
  // failures so each gets its own message in the UI below.
  const watchlistResult: WatchlistSaveResult =
    watchlist.companies.trim() !== ""
      ? await saveWatchlistCompanies(watchlist.companies, updateSources, fetchSources)
      : EMPTY_WATCHLIST_RESULT;

  // Bug 2 fix: await the round-trip so OnboardingGate reads
  // is_complete: true before navigate("/") fires.
  await refetchOnboardingStatus();

  return watchlistResult;
}
