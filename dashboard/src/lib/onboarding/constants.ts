/**
 * @packageDocumentation
 *
 * Constants shared across the onboarding wizard.
 *
 * @remarks
 * Step labels live here so the progress indicator and the parent shell can
 * import the same array. Timing constants (e.g., the watchlist redirect
 * delay) are centralised here so the integration test can pin them with
 * a single import.
 */

import knownSlugsData from "@/data/greenhouse_known_slugs.json";

/** Total number of wizard steps. */
export const STEP_COUNT = 7;

/** Step labels shown in the progress indicator. */
export const STEP_LABELS = [
  "About You",
  "Target Roles",
  "Resume",
  "Filters",
  "AI Provider",
  "Apply Prefs",
  "Watchlist",
] as const;

/**
 * How long the onboarding wizard keeps the watchlist warning on screen
 * before redirecting to the dashboard.
 *
 * @remarks
 * Long enough that a user can read 1–2 sentences of warning copy without
 * feeling rushed; short enough that a user who saw all-clear before the
 * warning was rendered is not stuck staring at a "Redirecting…" message.
 */
export const WATCHLIST_WARNING_REDIRECT_DELAY_MS = 3500;

/** Interval in ms between Codex auth status polls. */
export const CODEX_POLL_INTERVAL_MS = 3000;

/** Lookup table of known Greenhouse slugs, populated from the bundled JSON fixture. */
export const KNOWN_SLUGS: Record<string, string | null> = knownSlugsData.companies as Record<
  string,
  string | null
>;
