/**
 * @packageDocumentation
 *
 * Named design tokens for the AutoApply dashboard.
 *
 * @remarks
 * All color values are sourced from the Material Design 3 color scheme
 * generated for the AutoApply indigo palette. Import these constants
 * instead of using raw hex strings in components.
 */

/** Primary indigo brand color — used for active states, buttons, accents. */
export const COLOR_PRIMARY = "#4648d4" as const;

/** Lighter indigo used for primary container elements and donut chart segments. */
export const COLOR_PRIMARY_CONTAINER = "#6063ee" as const;

/** Very light indigo — background for active nav pills. */
export const COLOR_PRIMARY_FIXED = "#e1e0ff" as const;

/** Main text color on light backgrounds. */
export const COLOR_ON_SURFACE = "#191c1d" as const;

/** Secondary text / icon color. */
export const COLOR_ON_SURFACE_VARIANT = "#464554" as const;

/** Muted label color for sub-text and dividers. */
export const COLOR_OUTLINE = "#767586" as const;

/** Border color for cards and dividers. */
export const COLOR_OUTLINE_VARIANT = "#c7c4d7" as const;

/** Page and surface background. */
export const COLOR_SURFACE = "#f8f9fa" as const;

/** White surface — card backgrounds. */
export const COLOR_SURFACE_CONTAINER_LOWEST = "#ffffff" as const;

/** Very light gray — sidebar nav hover, budget widget background. */
export const COLOR_SURFACE_CONTAINER_LOW = "#f3f4f5" as const;

/** Light gray — progress bar tracks and muted containers. */
export const COLOR_SURFACE_CONTAINER = "#edeeef" as const;

/** Slightly darker gray — used for progress track fills. */
export const COLOR_SURFACE_CONTAINER_HIGH = "#e7e8e9" as const;

/** Secondary navy indigo — used for Workday segment in donut chart. */
export const COLOR_SECONDARY = "#4953bc" as const;

/** Error / destructive red. */
export const COLOR_ERROR = "#ba1a1a" as const;

/** Light error background for badges. */
export const COLOR_ERROR_CONTAINER = "#ffdad6" as const;

/** Error badge text color. */
export const COLOR_ON_ERROR_CONTAINER = "#93000a" as const;

/** Warm peach — used for JobSpy segment in source breakdown donut. */
export const COLOR_JOBSPY_SEGMENT = "#ffd4b8" as const;

/** Amber — border for warning banners. */
export const COLOR_WARNING = "#7c5800" as const;

/** Light amber — background for warning banners. */
export const COLOR_WARNING_CONTAINER = "#fff3e0" as const;

/** Dark amber — text inside warning banners. */
export const COLOR_ON_WARNING_CONTAINER = "#4e3600" as const;

/** Green — success status indicators. */
export const COLOR_SUCCESS = "#2e7d32" as const;

/** Light green — background for success banners. */
export const COLOR_SUCCESS_CONTAINER = "#e8f5e9" as const;

/** Dark green — text inside success banners. */
export const COLOR_ON_SUCCESS_CONTAINER = "#1b5e20" as const;

/** Fixed sidebar width in pixels. */
export const SIDEBAR_WIDTH_PX = 220 as const;

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
