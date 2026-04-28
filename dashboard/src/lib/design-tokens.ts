/**
 * @packageDocumentation
 *
 * Named design tokens for the AutoApply dashboard.
 *
 * @remarks
 * All color values use the pastel lavender/white palette defined in
 * `index.css`. These constants are referenced by components that need
 * inline styles (e.g. Recharts, dynamic backgrounds). Prefer Tailwind
 * utility classes where possible; use these only when inline is required.
 *
 * oklch values are converted to approximate hex for inline-style contexts
 * where oklch() may not be supported (e.g. SVG charts, third-party libs).
 */

/** Primary soft lavender — buttons, active states, accents. */
export const COLOR_PRIMARY = "#7c6bc4" as const;

/** Lighter lavender — primary container elements, chart segments. */
export const COLOR_PRIMARY_CONTAINER = "#a594de" as const;

/** Very light lavender — background for active nav pills, badges. */
export const COLOR_PRIMARY_FIXED = "#ede8ff" as const;

/** Dimmed lavender fixed — subtle emphasis backgrounds. */
export const COLOR_PRIMARY_FIXED_DIM = "#cfc2f0" as const;

/** Main text color — dark purple-gray on light backgrounds. */
export const COLOR_ON_SURFACE = "#2a2438" as const;

/** Secondary text / icon color — medium purple-gray. */
export const COLOR_ON_SURFACE_VARIANT = "#6b6280" as const;

/** Muted label color for sub-text and dividers. */
export const COLOR_OUTLINE = "#9085a8" as const;

/** Lighter border/divider color. */
export const COLOR_OUTLINE_VARIANT = "#c8c1d8" as const;

/** Page and surface background — off-white with lavender tint. */
export const COLOR_SURFACE = "#faf8fe" as const;

/** Card backgrounds — near-white. */
export const COLOR_SURFACE_CONTAINER_LOWEST = "#fdfcff" as const;

/** Sidebar hover, budget widget background. */
export const COLOR_SURFACE_CONTAINER_LOW = "#f5f2fa" as const;

/** Muted containers, progress bar tracks. */
export const COLOR_SURFACE_CONTAINER = "#efecf5" as const;

/** Slightly darker container for tracks. */
export const COLOR_SURFACE_CONTAINER_HIGH = "#e9e5f0" as const;

/** Secondary muted violet — chart segments, accents. */
export const COLOR_SECONDARY = "#7563b0" as const;

/** Tertiary sage green — complementary accent for charts. */
export const COLOR_TERTIARY = "#6a9a78" as const;

/** Warm blush — fourth chart color for variety. */
export const COLOR_BLUSH = "#c09090" as const;

/** Error / destructive — warm but softened red. */
export const COLOR_ERROR = "#c44040" as const;

/** Light error background for badges. */
export const COLOR_ERROR_CONTAINER = "#fce8e6" as const;

/** Error badge text color. */
export const COLOR_ON_ERROR_CONTAINER = "#6e1a1a" as const;

/** Warm peach — chart segment for JobSpy source. */
export const COLOR_JOBSPY_SEGMENT = "#e8c4a8" as const;

/** Amber warning. */
export const COLOR_WARNING = "#a07828" as const;

/** Light amber warning background. */
export const COLOR_WARNING_CONTAINER = "#fdf4e4" as const;

/** Dark amber warning text. */
export const COLOR_ON_WARNING_CONTAINER = "#5c4418" as const;

/** Sage success. */
export const COLOR_SUCCESS = "#4a8a58" as const;

/** Light sage success background. */
export const COLOR_SUCCESS_CONTAINER = "#e8f5ec" as const;

/** Dark sage success text. */
export const COLOR_ON_SUCCESS_CONTAINER = "#1e4a28" as const;

/** Fixed sidebar width in pixels. */
export const SIDEBAR_WIDTH_PX = 240 as const;

/** Settings panel slide-out width in pixels. */
export const SETTINGS_PANEL_WIDTH_PX = 480 as const;

/** z-index for the settings backdrop overlay. */
export const Z_SETTINGS_BACKDROP = 60 as const;

/** z-index for the settings panel itself (above backdrop). */
export const Z_SETTINGS_PANEL = 70 as const;

/** z-index for the sidebar. */
export const Z_SIDEBAR = 50 as const;

/** z-index for the top bar. */
export const Z_TOPBAR = 40 as const;

/** z-index for the command bar overlay. */
export const Z_COMMAND_BAR = 80 as const;
