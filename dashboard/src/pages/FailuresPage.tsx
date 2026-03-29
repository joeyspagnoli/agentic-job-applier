/**
 * @packageDocumentation
 *
 * Failures page — displays pipeline error monitoring for the AutoApply dashboard.
 *
 * @remarks
 * Shows four KPI stat cards, a search/filter bar, and a data table with
 * expandable rows. Each expanded row reveals a 3-column detail panel:
 * job details, a dark error trace terminal, and a retry history timeline.
 *
 * All data is currently hardcoded mock values matching the Stitch design mockup.
 * Replace each constant with an API call once the FastAPI backend is wired up.
 */

import type { CSSProperties, JSX } from "react";
import { useState } from "react";
import {
  COLOR_PRIMARY,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_SURFACE_CONTAINER_HIGH,
  COLOR_ERROR,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Local color constants — not in design-tokens.ts because they are page-specific.
// ---------------------------------------------------------------------------

/** Indigo primary-fixed-dim: used for model/context info lines in error traces. */
const COLOR_TRACE_INFO = "#c0c1ff" as const;

/** Green-400: used for suggestion lines in error traces. */
const COLOR_TRACE_SUGGESTION = "#4ade80" as const;

/** Green-600: used for "retry succeeded" sub-text in stat cards. */
const COLOR_SUCCESS_TEXT = "#16a34a" as const;

/** Green-500: used for the "task_alt" icon in the retry success rate card. */
const COLOR_SUCCESS_ICON = "#22c55e" as const;

/** Inverse-on-surface: default text color inside the dark error trace terminal. */
const COLOR_TRACE_DEFAULT = "#f0f1f2" as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Pipeline stages that can produce failures. */
type FailureStage = "TAILORING" | "REVIEW" | "APPLY" | "DISCOVERY" | "GATE";

/** Current retry status of a failed job run. */
type FailureStatus = "PENDING" | "EXHAUSTED" | "RETRYING";

/** A single failure record shown in the table. */
interface FailureRecord {
  /** Unique identifier for this failure record. */
  readonly id: number;
  /** Pipeline stage where the failure occurred. */
  readonly stage: FailureStage;
  /** Company name. */
  readonly company: string;
  /** Job position title. */
  readonly position: string;
  /** Short error code shown in the table cell. */
  readonly errorCode: string;
  /** Number of attempts made so far. */
  readonly attempts: number;
  /** Maximum allowed attempts before the run is marked EXHAUSTED. */
  readonly maxAttempts: number;
  /** Human-readable time since failure (e.g. "2m ago"). */
  readonly time: string;
  /** Current retry status. */
  readonly status: FailureStatus;
  /** Full error trace lines shown in the expanded panel's terminal card. */
  readonly errorTrace: readonly string[];
  /** Ordered retry history entries shown in the timeline column. */
  readonly retryHistory: readonly RetryEntry[];
  /** ATS platform where the job was sourced (e.g. "GREENHOUSE"). */
  readonly platform: string;
}

/** A single entry in the retry history timeline column. */
interface RetryEntry {
  /** Distinguishes a past failure from an upcoming scheduled attempt. */
  readonly kind: "failed" | "scheduled";
  /** Human-readable label, e.g. "Attempt 1: Failed". */
  readonly label: string;
  /** Timestamp string shown below the label. */
  readonly timestamp: string;
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

/**
 * Configuration for each stat card in the top row.
 *
 * @remarks
 * Typed with `as const satisfies` so each `subTextColor` / `iconColor` stays
 * a literal string while the array shape is validated against the inline type.
 */
const STAT_CARDS = [
  {
    label: "Total Failures",
    value: "23",
    subText: "Across all stages",
    subTextColor: COLOR_ERROR,
    icon: "report",
    iconColor: COLOR_ERROR,
    iconFilled: true,
  },
  {
    label: "Last 24 Hours",
    value: "5",
    subText: "↑ 2 from yesterday",
    subTextColor: COLOR_ON_SURFACE_VARIANT,
    icon: "schedule",
    iconColor: COLOR_OUTLINE,
    iconFilled: false,
  },
  {
    label: "Most Failing Stage",
    value: "Tailoring",
    subText: "14 of 23 failures (61%)",
    subTextColor: COLOR_ON_SURFACE_VARIANT,
    icon: "architecture",
    iconColor: COLOR_OUTLINE,
    iconFilled: false,
  },
  {
    label: "Retry Success Rate",
    value: "68%",
    subText: "17 of 25 retries succeeded",
    subTextColor: COLOR_SUCCESS_TEXT,
    icon: "task_alt",
    iconColor: COLOR_SUCCESS_ICON,
    iconFilled: false,
  },
] as const satisfies readonly {
  label: string;
  value: string;
  subText: string;
  subTextColor: string;
  icon: string;
  iconColor: string;
  iconFilled: boolean;
}[];

/** Mock failure records. Replace with API call when the FastAPI backend is ready. */
const FAILURE_RECORDS: readonly FailureRecord[] = [
  {
    id: 1,
    stage: "TAILORING",
    company: "Google",
    position: "Senior Product Designer",
    errorCode: "TOKEN_LIMIT_EXCEEDED",
    attempts: 2,
    maxAttempts: 3,
    time: "2m ago",
    status: "RETRYING",
    platform: "GREENHOUSE",
    errorTrace: [
      "TailorWorker.run() failed at step: llm_content_generation",
      "Error: TOKEN_LIMIT_EXCEEDED",
      "Model: gpt-4o-mini | Tokens requested: 14,832 | Limit: 8,192",
      "Resume YAML size: 4.2KB | Job description: 6.1KB",
      "// Suggestion: Reduce candidate profile length or enable chunked processing",
    ],
    retryHistory: [
      { kind: "failed", label: "Attempt 1: Failed", timestamp: "Oct 24, 14:02:11" },
      { kind: "failed", label: "Attempt 2: Failed", timestamp: "Oct 24, 14:15:45" },
      { kind: "scheduled", label: "Next: Scheduled", timestamp: "Oct 24, 16:30:00 (In 2h)" },
    ],
  },
  {
    id: 2,
    stage: "REVIEW",
    company: "Stripe",
    position: "Lead Software Architect",
    errorCode: "TIMEOUT_004_GATEWAY",
    attempts: 1,
    maxAttempts: 3,
    time: "14m ago",
    status: "RETRYING",
    platform: "WORKDAY",
    errorTrace: [
      "ReviewWorker.run() failed at step: gateway_response",
      "Error: TIMEOUT_004_GATEWAY",
      "Timeout after 30s waiting for response",
      "// Suggestion: Retry with exponential backoff",
    ],
    retryHistory: [
      { kind: "failed", label: "Attempt 1: Failed", timestamp: "Oct 24, 13:48:22" },
      { kind: "scheduled", label: "Next: Scheduled", timestamp: "Oct 24, 14:18:22 (In 30m)" },
    ],
  },
  {
    id: 3,
    stage: "TAILORING",
    company: "Datadog",
    position: "Backend Engineer",
    errorCode: "JSON_PARSE_ERR",
    attempts: 3,
    maxAttempts: 3,
    time: "38m ago",
    status: "EXHAUSTED",
    platform: "LEVER",
    errorTrace: [
      "TailorWorker.run() failed at step: resume_json_serialization",
      "Error: JSON_PARSE_ERR",
      "Unexpected token at position 1842",
      "// Suggestion: Validate resume YAML for special characters",
    ],
    retryHistory: [
      { kind: "failed", label: "Attempt 1: Failed", timestamp: "Oct 24, 13:20:05" },
      { kind: "failed", label: "Attempt 2: Failed", timestamp: "Oct 24, 13:33:18" },
      { kind: "failed", label: "Attempt 3: Failed", timestamp: "Oct 24, 13:47:44" },
    ],
  },
  {
    id: 4,
    stage: "APPLY",
    company: "Figma",
    position: "Lead Systems Architect",
    errorCode: "CDP_CONNECTION_RESET",
    attempts: 1,
    maxAttempts: 3,
    time: "1h ago",
    status: "RETRYING",
    platform: "ASHBY",
    errorTrace: [
      "ApplyWorker.run() failed at step: browser_submit",
      "Error: CDP_CONNECTION_RESET",
      "Chrome DevTools Protocol connection dropped mid-session",
      "// Suggestion: Increase CDP socket timeout or restart browser pool",
    ],
    retryHistory: [
      { kind: "failed", label: "Attempt 1: Failed", timestamp: "Oct 24, 13:02:55" },
      { kind: "scheduled", label: "Next: Scheduled", timestamp: "Oct 24, 14:02:55 (In 1h)" },
    ],
  },
  {
    id: 5,
    stage: "TAILORING",
    company: "Coinbase",
    position: "Product Manager",
    errorCode: "LATEX_COMPILE_FAIL",
    attempts: 2,
    maxAttempts: 3,
    time: "3h ago",
    status: "RETRYING",
    platform: "GREENHOUSE",
    errorTrace: [
      "TailorWorker.run() failed at step: pdf_render",
      "Error: LATEX_COMPILE_FAIL",
      "pdflatex exited with code 1 — undefined control sequence \\jobTitle",
      "// Suggestion: Check LaTeX template for undefined commands",
    ],
    retryHistory: [
      { kind: "failed", label: "Attempt 1: Failed", timestamp: "Oct 24, 11:14:33" },
      { kind: "failed", label: "Attempt 2: Failed", timestamp: "Oct 24, 11:28:07" },
      { kind: "scheduled", label: "Next: Scheduled", timestamp: "Oct 24, 14:28:07 (In 3h)" },
    ],
  },
] as const satisfies readonly FailureRecord[];

// ---------------------------------------------------------------------------
// Helper maps
// ---------------------------------------------------------------------------

/**
 * Tailwind class pairs mapping each pipeline stage to its badge color.
 *
 * @remarks
 * Using Tailwind classes here (not inline styles) because these are static
 * compile-time values that benefit from purge optimization.
 */
const STAGE_BADGE_CLASSES: Record<FailureStage, string> = {
  TAILORING: "bg-purple-100 text-purple-700",
  REVIEW: "bg-blue-100 text-blue-700",
  APPLY: "bg-amber-100 text-amber-700",
  DISCOVERY: "bg-green-100 text-green-700",
  GATE: "bg-rose-100 text-rose-700",
} as const satisfies Record<FailureStage, string>;

/** Filter button labels rendered beside the search input. */
const FILTER_LABELS = ["Stage", "Status", "Time Range"] as const;

/** Table column headers rendered in the thead row. */
const TABLE_COLUMNS = [
  "Stage",
  "Company",
  "Position",
  "Error",
  "Attempts",
  "Time",
  "Actions",
] as const;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Props for {@link FailureStatCard}. */
interface FailureStatCardProps {
  /** Uppercase label shown above the value. */
  readonly label: string;
  /** Large primary metric value. */
  readonly value: string;
  /** Smaller sub-text shown below the value. */
  readonly subText: string;
  /** CSS color string applied to the sub-text. */
  readonly subTextColor: string;
  /** Material Symbols icon ligature name. */
  readonly icon: string;
  /** CSS color string applied to the icon. */
  readonly iconColor: string;
  /** When `true`, renders the icon in filled variant via `font-variation-settings`. */
  readonly iconFilled: boolean;
}

/**
 * A single KPI stat card for the Failures page top row.
 *
 * @param props - See {@link FailureStatCardProps}.
 * @returns A white rounded card element with label, value, sub-text, and icon.
 */
function FailureStatCard(props: FailureStatCardProps): JSX.Element {
  const { label, value, subText, subTextColor, icon, iconColor, iconFilled } = props;
  return (
    <div
      className="bg-white p-6 rounded-xl border"
      style={{
        boxShadow: "0 4px 20px -4px rgba(0,0,0,0.05)",
        borderColor: `${COLOR_OUTLINE_VARIANT}1A`,
      }}
    >
      <div className="flex justify-between items-start mb-4">
        <span
          className="text-xs font-bold tracking-wider uppercase"
          style={{ color: COLOR_OUTLINE }}
        >
          {label}
        </span>
        <span
          className="material-symbols-outlined"
          style={{
            color: iconColor,
            fontVariationSettings: iconFilled ? "'FILL' 1" : "'FILL' 0",
          }}
        >
          {icon}
        </span>
      </div>
      <div className="text-3xl font-bold mb-1" style={{ color: COLOR_ON_SURFACE }}>
        {value}
      </div>
      <p className="text-xs font-medium" style={{ color: subTextColor }}>
        {subText}
      </p>
    </div>
  );
}

/** Props for {@link AttemptDots}. */
interface AttemptDotsProps {
  /** Number of attempts made so far. */
  readonly attempts: number;
  /** Maximum attempts allowed before the run is EXHAUSTED. */
  readonly maxAttempts: number;
  /** When `true`, filled dots render in red instead of primary indigo. */
  readonly exhausted: boolean;
}

/**
 * Dot indicators showing attempt progress (e.g. ●●○ 2/3).
 *
 * @param props - See {@link AttemptDotsProps}.
 * @returns A flex row of colored dots followed by an "N/M" label.
 */
function AttemptDots(props: AttemptDotsProps): JSX.Element {
  const { attempts, maxAttempts, exhausted } = props;
  const dotIndices = Array.from({ length: maxAttempts }, (_, i) => i);

  function dotColor(index: number): string {
    const isFilled = index < attempts;
    if (!isFilled) return COLOR_SURFACE_CONTAINER_HIGH;
    return exhausted ? COLOR_ERROR : COLOR_PRIMARY;
  }

  return (
    <div className="flex space-x-1 items-center">
      {dotIndices.map((i) => (
        <div key={i} className="w-2 h-2 rounded-full" style={{ backgroundColor: dotColor(i) }} />
      ))}
      <span className="ml-2 text-xs font-medium" style={{ color: COLOR_OUTLINE }}>
        {attempts}/{maxAttempts}
      </span>
    </div>
  );
}

/** Props for {@link RetryTimeline}. */
interface RetryTimelineProps {
  /** Ordered list of retry history entries for this failure record. */
  readonly entries: readonly RetryEntry[];
}

/**
 * Vertical timeline of retry attempts shown in the expanded detail panel.
 *
 * @param props - See {@link RetryTimelineProps}.
 * @returns A stacked list of timeline nodes connected by thin vertical lines.
 */
function RetryTimeline(props: RetryTimelineProps): JSX.Element {
  const { entries } = props;

  return (
    <div className="space-y-4">
      {entries.map((entry, index) => {
        const isLast = index === entries.length - 1;

        if (entry.kind === "failed") {
          return (
            <div key={index} className="flex items-start space-x-3">
              <div className="relative flex flex-col items-center">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{
                    backgroundColor: COLOR_ERROR,
                    // Simulate ring-4 ring-error/10 without relying on a Tailwind color alias.
                    boxShadow: `0 0 0 4px ${COLOR_ERROR}1A`,
                  }}
                />
                {!isLast && (
                  <div
                    className="w-px h-8 my-1"
                    style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}4D` }}
                  />
                )}
              </div>
              <div>
                <p className="text-[11px] font-bold" style={{ color: COLOR_ON_SURFACE }}>
                  {entry.label}
                </p>
                <p className="text-[10px]" style={{ color: COLOR_OUTLINE }}>
                  {entry.timestamp}
                </p>
              </div>
            </div>
          );
        }

        return (
          <div key={index} className="flex items-start space-x-3">
            <span
              className="material-symbols-outlined text-[16px]"
              style={{ color: COLOR_OUTLINE }}
            >
              schedule
            </span>
            <div>
              <p className="text-[11px] font-bold" style={{ color: COLOR_OUTLINE }}>
                {entry.label}
              </p>
              <p className="text-[10px]" style={{ color: COLOR_OUTLINE }}>
                {entry.timestamp}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Props for {@link ErrorTraceCard}. */
interface ErrorTraceCardProps {
  /** Lines of the error trace to render in order. */
  readonly lines: readonly string[];
}

/**
 * Resolves the inline style for a single line in the error trace terminal.
 *
 * @remarks
 * Line indices map to fixed semantic roles:
 * - 0: neutral default text
 * - 1: error line (red)
 * - 2: model/context info (indigo primary-fixed-dim)
 * - 3: neutral default text
 * - 4: suggestion (green, italic, bold)
 *
 * @param lineIndex - Zero-based index of the line within the trace.
 * @returns Inline CSS properties for that line.
 */
function resolveTraceLineStyle(lineIndex: number): CSSProperties {
  if (lineIndex === 1) {
    return { color: COLOR_ERROR, fontWeight: 700, marginTop: "0.5rem" };
  }
  if (lineIndex === 2) {
    return { color: COLOR_TRACE_INFO };
  }
  if (lineIndex === 4) {
    return {
      color: COLOR_TRACE_SUGGESTION,
      fontStyle: "italic",
      fontWeight: 700,
      marginTop: "0.5rem",
    };
  }
  return { color: COLOR_TRACE_DEFAULT };
}

/**
 * Dark terminal card showing the full error trace for an expanded failure row.
 *
 * @param props - See {@link ErrorTraceCardProps}.
 * @returns A dark-background monospace code block with semantically colored lines.
 */
function ErrorTraceCard(props: ErrorTraceCardProps): JSX.Element {
  const { lines } = props;
  return (
    <div
      className="p-5 rounded-xl font-mono text-xs leading-relaxed shadow-lg"
      style={{ backgroundColor: COLOR_ON_SURFACE, color: COLOR_TRACE_DEFAULT }}
    >
      <div
        className="flex items-center space-x-2 mb-3 pb-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
      >
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLOR_ERROR }} />
        <span className="font-bold">Error Trace</span>
      </div>
      <div className="opacity-90">
        {lines.map((line, index) => (
          <p key={index} style={resolveTraceLineStyle(index)}>
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

/** Props for {@link ExpandedDetailPanel}. */
interface ExpandedDetailPanelProps {
  /** The failure record whose details are shown in the expanded panel. */
  readonly record: FailureRecord;
  /** Called when the "Dismiss & Acknowledge" button is clicked. */
  readonly onDismiss: () => void;
  /** Called when the "Retry Now" button is clicked. */
  readonly onRetry: () => void;
}

/**
 * Full-width expanded detail panel rendered below an active table row.
 *
 * @remarks
 * Spans all 7 table columns with a 12-column CSS grid divided into
 * job details (3 cols), error terminal (6 cols), and retry timeline (3 cols).
 *
 * @param props - See {@link ExpandedDetailPanelProps}.
 * @returns A `<tr>` element spanning all columns with the 3-column detail layout.
 */
function ExpandedDetailPanel(props: ExpandedDetailPanelProps): JSX.Element {
  const { record, onDismiss, onRetry } = props;
  return (
    <tr style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}4D` }}>
      <td
        className="px-8 py-8"
        colSpan={7}
        style={{ borderTop: `1px solid ${COLOR_OUTLINE_VARIANT}1A` }}
      >
        <div className="grid grid-cols-12 gap-10">
          {/* Left: job details */}
          <div className="col-span-3 space-y-6">
            <div>
              <h4
                className="text-[10px] font-bold tracking-widest uppercase mb-4"
                style={{ color: COLOR_OUTLINE }}
              >
                Job Details
              </h4>
              <div className="flex items-center space-x-3 mb-2">
                <div
                  className="w-8 h-8 rounded flex items-center justify-center border shadow-sm text-xs font-bold"
                  style={{
                    backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
                    borderColor: `${COLOR_OUTLINE_VARIANT}33`,
                    color: COLOR_ON_SURFACE_VARIANT,
                  }}
                >
                  {record.company[0]}
                </div>
                <div>
                  <div className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                    {record.company}
                  </div>
                  <div className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    {record.position}
                  </div>
                </div>
              </div>
              <div className="flex items-center space-x-2 mt-4">
                <span
                  className="px-2 py-0.5 rounded text-[10px] font-bold border uppercase"
                  style={{
                    backgroundColor: COLOR_SURFACE_CONTAINER_HIGH,
                    color: COLOR_ON_SURFACE_VARIANT,
                    borderColor: `${COLOR_OUTLINE_VARIANT}4D`,
                  }}
                >
                  {record.platform}
                </span>
                <a
                  className="text-[10px] font-bold flex items-center hover:underline"
                  href="#"
                  style={{ color: COLOR_PRIMARY }}
                >
                  VIEW JOB POSTING
                  <span className="material-symbols-outlined text-[12px] ml-1">open_in_new</span>
                </a>
              </div>
            </div>
            <div>
              <span
                className="text-[10px] font-bold tracking-widest uppercase block mb-2"
                style={{ color: COLOR_OUTLINE }}
              >
                Status
              </span>
              <span className="px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-[10px] font-bold tracking-wider">
                TAILOR_PENDING
              </span>
            </div>
          </div>

          {/* Center: error trace terminal */}
          <div className="col-span-6">
            <h4
              className="text-[10px] font-bold tracking-widest uppercase mb-4"
              style={{ color: COLOR_OUTLINE }}
            >
              Error Details
            </h4>
            <ErrorTraceCard lines={record.errorTrace} />
          </div>

          {/* Right: retry history timeline */}
          <div className="col-span-3">
            <h4
              className="text-[10px] font-bold tracking-widest uppercase mb-4"
              style={{ color: COLOR_OUTLINE }}
            >
              Retry History
            </h4>
            <RetryTimeline entries={record.retryHistory} />
          </div>
        </div>

        {/* Action buttons */}
        <div
          className="flex justify-end mt-8 pt-6 space-x-3"
          style={{ borderTop: `1px solid ${COLOR_OUTLINE_VARIANT}1A` }}
        >
          <button
            className="px-6 py-2.5 rounded-lg border text-sm font-bold transition-colors hover:bg-white"
            style={{
              borderColor: `${COLOR_OUTLINE_VARIANT}80`,
              color: COLOR_ON_SURFACE_VARIANT,
            }}
            onClick={onDismiss}
          >
            Dismiss &amp; Acknowledge
          </button>
          <button
            className="px-6 py-2.5 rounded-lg text-white text-sm font-bold shadow-md transition-all active:scale-95"
            style={{ backgroundColor: COLOR_PRIMARY }}
            onClick={onRetry}
          >
            Retry Now
          </button>
        </div>
      </td>
    </tr>
  );
}

/** Props for {@link FailureTableRow}. */
interface FailureTableRowProps {
  /** The failure record this row represents. */
  readonly record: FailureRecord;
  /** Whether the expanded detail panel is currently visible for this row. */
  readonly isExpanded: boolean;
  /** Called when the row body is clicked to toggle the detail panel. */
  readonly onToggle: () => void;
  /** Called when "Dismiss & Acknowledge" is clicked in the expanded panel. */
  readonly onDismiss: () => void;
  /** Called when "Retry Now" is clicked in the expanded panel. */
  readonly onRetry: () => void;
}

/**
 * A single row in the failures table, optionally followed by an expanded detail panel.
 *
 * @param props - See {@link FailureTableRowProps}.
 * @returns One `<tr>` for the summary row, plus a second `<tr>` when expanded.
 */
function FailureTableRow(props: FailureTableRowProps): JSX.Element {
  const { record, isExpanded, onToggle, onDismiss, onRetry } = props;
  const isExhausted = record.status === "EXHAUSTED";
  const stageBadgeClass = STAGE_BADGE_CLASSES[record.stage];

  function handleRetryClick(event: React.MouseEvent): void {
    event.stopPropagation();
  }

  function handleDismissClick(event: React.MouseEvent): void {
    event.stopPropagation();
  }

  return (
    <>
      <tr
        className="transition-colors cursor-pointer"
        style={{
          opacity: isExhausted ? 0.6 : 1,
          borderLeft: isExpanded ? `4px solid ${COLOR_PRIMARY}` : "4px solid transparent",
        }}
        onClick={onToggle}
      >
        <td className="px-6 py-5">
          <span
            className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider ${stageBadgeClass}`}
          >
            {record.stage}
          </span>
        </td>
        <td className="px-6 py-5 font-semibold" style={{ color: COLOR_ON_SURFACE }}>
          {record.company}
        </td>
        <td className="px-6 py-5" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {record.position}
        </td>
        <td className="px-6 py-5">
          <code
            className="text-xs font-mono font-semibold px-1.5 py-0.5 rounded"
            style={{ color: COLOR_ERROR, backgroundColor: `${COLOR_ERROR}1A` }}
          >
            {record.errorCode}
          </code>
        </td>
        <td className="px-6 py-5">
          <AttemptDots
            attempts={record.attempts}
            maxAttempts={record.maxAttempts}
            exhausted={isExhausted}
          />
        </td>
        <td className="px-6 py-5 text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {record.time}
        </td>
        <td className="px-6 py-5 text-right space-x-3">
          <button
            className="transition-transform hover:scale-110 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ color: isExhausted ? `${COLOR_OUTLINE}66` : COLOR_PRIMARY }}
            disabled={isExhausted}
            onClick={handleRetryClick}
            aria-label="Retry"
          >
            <span className="material-symbols-outlined">replay</span>
          </button>
          <button
            className="transition-colors hover:scale-110"
            style={{ color: COLOR_OUTLINE }}
            onClick={handleDismissClick}
            aria-label="Dismiss"
          >
            <span className="material-symbols-outlined">cancel</span>
          </button>
        </td>
      </tr>
      {isExpanded && (
        <ExpandedDetailPanel record={record} onDismiss={onDismiss} onRetry={onRetry} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

/**
 * Failures page — pipeline error monitoring view.
 *
 * @remarks
 * Rendered at the `/failures` route inside {@link AppLayout}.
 * Manages `expandedRow` (which detail panel is open) and `searchQuery`
 * (the live filter applied to the table).
 *
 * @returns The failures page content element.
 */
export function FailuresPage(): JSX.Element {
  const [expandedRow, setExpandedRow] = useState<number | null>(FAILURE_RECORDS[0].id);
  const [searchQuery, setSearchQuery] = useState<string>("");

  function handleRowToggle(id: number): void {
    setExpandedRow((prev) => (prev === id ? null : id));
  }

  function handleDismiss(): void {
    setExpandedRow(null);
  }

  function handleRetry(): void {
    setExpandedRow(null);
  }

  function handleSearchChange(event: React.ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
  }

  const filteredRecords = FAILURE_RECORDS.filter((record) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      record.company.toLowerCase().includes(query) ||
      record.position.toLowerCase().includes(query) ||
      record.errorCode.toLowerCase().includes(query) ||
      record.stage.toLowerCase().includes(query)
    );
  });

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Row 1 — stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {STAT_CARDS.map((card) => (
          <FailureStatCard
            key={card.label}
            label={card.label}
            value={card.value}
            subText={card.subText}
            subTextColor={card.subTextColor}
            icon={card.icon}
            iconColor={card.iconColor}
            iconFilled={card.iconFilled}
          />
        ))}
      </div>

      {/* Row 2 — search + filter bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="w-2/5 relative">
          <span
            className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-sm"
            style={{ color: COLOR_OUTLINE }}
          >
            search
          </span>
          <input
            className="w-full rounded-full pl-12 pr-4 py-2.5 text-sm transition-all outline-none"
            style={{
              backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
              border: "1px solid transparent",
              color: COLOR_ON_SURFACE,
            }}
            placeholder="Search failures..."
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </div>
        <div className="flex items-center space-x-3">
          {FILTER_LABELS.map((label) => (
            <button
              key={label}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors text-sm font-medium"
              style={{ border: `1px solid ${COLOR_OUTLINE_VARIANT}80`, color: COLOR_ON_SURFACE }}
            >
              <span>{label}</span>
              <span className="material-symbols-outlined text-sm">expand_more</span>
            </button>
          ))}
        </div>
      </div>

      {/* Row 3 — data table */}
      <div
        className="bg-white rounded-xl border overflow-hidden"
        style={{
          boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
          borderColor: `${COLOR_OUTLINE_VARIANT}1A`,
        }}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}>
                {TABLE_COLUMNS.map((col) => (
                  <th
                    key={col}
                    className={`px-6 py-4 text-[10px] font-bold tracking-widest uppercase${col === "Actions" ? " text-right" : ""}`}
                    style={{ color: COLOR_OUTLINE }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody style={{ borderTop: `1px solid ${COLOR_OUTLINE_VARIANT}1A` }}>
              {filteredRecords.map((record) => (
                <FailureTableRow
                  key={record.id}
                  record={record}
                  isExpanded={expandedRow === record.id}
                  onToggle={() => {
                    handleRowToggle(record.id);
                  }}
                  onDismiss={handleDismiss}
                  onRetry={handleRetry}
                />
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div
          className="px-6 py-4 flex items-center justify-between"
          style={{
            backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}4D`,
            borderTop: `1px solid ${COLOR_OUTLINE_VARIANT}1A`,
          }}
        >
          <span className="text-xs font-medium" style={{ color: COLOR_OUTLINE }}>
            Showing 1–{filteredRecords.length} of {FAILURE_RECORDS.length} failures
          </span>
          <div className="flex items-center space-x-2">
            <button
              className="p-1 rounded transition-colors disabled:opacity-30"
              style={{ color: COLOR_OUTLINE }}
              disabled
              aria-label="Previous page"
            >
              <span className="material-symbols-outlined">chevron_left</span>
            </button>
            <button
              className="w-8 h-8 rounded text-xs font-bold text-white"
              style={{ backgroundColor: COLOR_PRIMARY }}
              aria-current="page"
            >
              1
            </button>
            <button
              className="w-8 h-8 rounded text-xs font-bold transition-colors"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
              aria-label="Page 2"
            >
              2
            </button>
            <button
              className="p-1 rounded transition-colors"
              style={{ color: COLOR_OUTLINE }}
              aria-label="Next page"
            >
              <span className="material-symbols-outlined">chevron_right</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
