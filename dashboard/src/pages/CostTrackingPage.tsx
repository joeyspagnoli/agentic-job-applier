/**
 * @packageDocumentation
 *
 * Cost Tracking page — pipeline spend analytics and recent failure triage.
 *
 * @remarks
 * Displays three KPI stat cards, a daily spend bar chart with a 7-day /
 * 30-day / all-time range toggle, a horizontal Cost by Stage breakdown, and
 * a compact Recent Failures table. All data is hardcoded mock values matching
 * the Stitch design reference. No API integration yet.
 */

import type { JSX } from "react";
import { useState } from "react";
import { COLOR_PRIMARY, COLOR_PRIMARY_CONTAINER } from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Which time range the spend-trend chart is currently showing. */
type SpendRangeFilter = "7d" | "30d" | "all";

/** Pipeline stages that accumulate LLM costs. */
type PipelineStage = "DISCOVERY" | "TAILORING" | "REVIEW" | "APPLY";

/** Stage labels that appear on recent-failure badges. */
type FailureStage = "TAILORING" | "REVIEW" | "GATE" | "APPLY" | "DISCOVERY";

/** One bar in the spend-trend chart. */
interface SpendBarDatum {
  /** X-axis label (day name or "TODAY"). */
  readonly label: string;
  /** Bar height as a percentage of the chart container (0–100). */
  readonly heightPct: number;
  /** Whether this bar represents the current day. */
  readonly isToday: boolean;
  /** Tooltip dollar amount shown on hover, only for the current day. */
  readonly amountLabel?: string;
}

/** A single pipeline stage and its share of total API spend. */
interface StageSpend {
  /** Human-readable stage name in UPPER_SNAKE_CASE. */
  readonly stage: PipelineStage;
  /** Formatted dollar amount, e.g. "$28.40". */
  readonly amount: string;
  /** Width of the progress bar as a percentage (0–100). */
  readonly barWidthPct: number;
}

/** One row in the recent-failures compact table. */
interface RecentFailure {
  /** Unique record identifier. */
  readonly id: number;
  /** Pipeline stage that produced this failure. */
  readonly stage: FailureStage;
  /** Tailwind CSS classes for the stage badge background + text color. */
  readonly stageBadgeClass: string;
  /** Truncated job title shown in the table row. */
  readonly jobTitle: string;
  /** Short error code displayed in a monospace red code span. */
  readonly errorCode: string;
  /** Human-readable elapsed time, e.g. "2m ago". */
  readonly time: string;
}

// ---------------------------------------------------------------------------
// Mock data constants
// ---------------------------------------------------------------------------

/** Formatted total month-to-date API spend. */
const TOTAL_SPEND = "$47.23" as const;

/** Formatted average LLM cost per submitted application. */
const AVG_COST_PER_APP = "$0.24" as const;

/** Number of LLM API calls made today. */
const API_CALLS_TODAY = 847 as const;

/** Bar heights for the "Last 7 days" spend trend chart. */
const SPEND_BARS_7D: readonly SpendBarDatum[] = [
  { label: "MON", heightPct: 40, isToday: false },
  { label: "TUE", heightPct: 65, isToday: false },
  { label: "WED", heightPct: 55, isToday: false },
  { label: "THU", heightPct: 85, isToday: false },
  { label: "FRI", heightPct: 70, isToday: false },
  { label: "SAT", heightPct: 45, isToday: false },
  { label: "TODAY", heightPct: 95, isToday: true, amountLabel: "$9.42" },
] as const satisfies readonly SpendBarDatum[];

/** Bar heights for the "Last 30 days" spend trend chart. */
const SPEND_BARS_30D: readonly SpendBarDatum[] = [
  { label: "1", heightPct: 30, isToday: false },
  { label: "2", heightPct: 50, isToday: false },
  { label: "3", heightPct: 40, isToday: false },
  { label: "4", heightPct: 60, isToday: false },
  { label: "5", heightPct: 35, isToday: false },
  { label: "6", heightPct: 70, isToday: false },
  { label: "7", heightPct: 55, isToday: false },
  { label: "8", heightPct: 45, isToday: false },
  { label: "9", heightPct: 80, isToday: false },
  { label: "10", heightPct: 65, isToday: false },
  { label: "11", heightPct: 50, isToday: false },
  { label: "12", heightPct: 75, isToday: false },
  { label: "13", heightPct: 40, isToday: false },
  { label: "14", heightPct: 90, isToday: false },
  { label: "15", heightPct: 60, isToday: false },
  { label: "16", heightPct: 55, isToday: false },
  { label: "17", heightPct: 70, isToday: false },
  { label: "18", heightPct: 45, isToday: false },
  { label: "19", heightPct: 85, isToday: false },
  { label: "20", heightPct: 65, isToday: false },
  { label: "21", heightPct: 50, isToday: false },
  { label: "22", heightPct: 40, isToday: false },
  { label: "23", heightPct: 65, isToday: false },
  { label: "24", heightPct: 55, isToday: false },
  { label: "25", heightPct: 85, isToday: false },
  { label: "26", heightPct: 70, isToday: false },
  { label: "27", heightPct: 45, isToday: false },
  { label: "28", heightPct: 60, isToday: false },
  { label: "29", heightPct: 80, isToday: false },
  { label: "TODAY", heightPct: 95, isToday: true, amountLabel: "$9.42" },
] as const satisfies readonly SpendBarDatum[];

/** Bar heights for the "All time" spend trend chart (monthly aggregates). */
const SPEND_BARS_ALL: readonly SpendBarDatum[] = [
  { label: "Oct", heightPct: 20, isToday: false },
  { label: "Nov", heightPct: 35, isToday: false },
  { label: "Dec", heightPct: 50, isToday: false },
  { label: "Jan", heightPct: 45, isToday: false },
  { label: "Feb", heightPct: 60, isToday: false },
  { label: "Mar", heightPct: 95, isToday: true, amountLabel: "$47.23" },
] as const satisfies readonly SpendBarDatum[];

/** Cost breakdown across all active pipeline stages. */
const STAGE_COSTS: readonly StageSpend[] = [
  { stage: "DISCOVERY", amount: "$2.10", barWidthPct: 15 },
  { stage: "TAILORING", amount: "$28.40", barWidthPct: 85 },
  { stage: "REVIEW", amount: "$12.30", barWidthPct: 45 },
  { stage: "APPLY", amount: "$4.43", barWidthPct: 25 },
] as const satisfies readonly StageSpend[];

/** Recent failures for the compact triage table. */
const RECENT_FAILURES: readonly RecentFailure[] = [
  {
    id: 1,
    stage: "TAILORING",
    stageBadgeClass: "bg-red-50 text-red-600",
    jobTitle: "Senior Product De...",
    errorCode: "TOKEN_LIMIT_EXC...",
    time: "2m ago",
  },
  {
    id: 2,
    stage: "REVIEW",
    stageBadgeClass: "bg-indigo-50 text-indigo-600",
    jobTitle: "Lead Software Ar...",
    errorCode: "TIMEOUT_004_GAT...",
    time: "14m ago",
  },
] as const satisfies readonly RecentFailure[];

/** Maps each SpendRangeFilter key to its bar data array. */
const SPEND_BARS_BY_FILTER: Record<SpendRangeFilter, readonly SpendBarDatum[]> = {
  "7d": SPEND_BARS_7D,
  "30d": SPEND_BARS_30D,
  all: SPEND_BARS_ALL,
} as const satisfies Record<SpendRangeFilter, readonly SpendBarDatum[]>;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Props for {@link StatCard}. */
interface StatCardProps {
  /** Short all-caps label rendered above the primary value. */
  readonly label: string;
  /** Large primary value string, e.g. "$47.23" or "847". */
  readonly value: string;
  /** Material Symbols icon ligature name for the top-right icon. */
  readonly icon: string;
  /** Optional font-variation-settings style for filled icon variants. */
  readonly iconFilled?: boolean;
  /** Content rendered beneath the primary value (supports JSX). */
  readonly subtitle: JSX.Element | string;
}

/**
 * KPI stat card with label, large value, icon, and a subtitle line.
 *
 * @param props - {@link StatCardProps}
 * @returns A white rounded card with a top-right Material icon.
 */
function StatCard({
  label,
  value,
  icon,
  iconFilled = false,
  subtitle,
}: StatCardProps): JSX.Element {
  const iconStyle = iconFilled ? { fontVariationSettings: "'FILL' 1" } : undefined;

  return (
    <div
      className="bg-white p-8 rounded-xl"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <div className="flex items-center justify-between mb-4">
        <p className="text-[11px] font-bold text-on-surface-variant uppercase tracking-[0.05em]">
          {label}
        </p>
        <span
          className="material-symbols-outlined"
          style={{
            color: `${COLOR_PRIMARY_CONTAINER}66`,
            ...iconStyle,
          }}
        >
          {icon}
        </span>
      </div>
      <h2 className="text-4xl font-extrabold text-on-surface mb-2">{value}</h2>
      <div className="text-xs">{subtitle}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link SpendBar}. */
interface SpendBarProps {
  /** Data for this individual bar. */
  readonly datum: SpendBarDatum;
}

/**
 * One vertical bar in the daily spend trend chart.
 *
 * @param props - {@link SpendBarProps}
 * @returns A flex column with the colored bar and day label.
 */
function SpendBar({ datum }: SpendBarProps): JSX.Element {
  const barStyle = datum.isToday
    ? { backgroundColor: COLOR_PRIMARY, height: `${datum.heightPct}%` }
    : {
        backgroundColor: `${COLOR_PRIMARY}1A`,
        height: `${datum.heightPct}%`,
      };

  return (
    <div className="flex-1 flex flex-col items-center gap-2 group">
      <div className="w-full rounded-t-lg transition-all relative" style={barStyle}>
        {datum.amountLabel !== undefined && (
          <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-on-surface text-white px-2 py-1 rounded text-[10px] font-bold opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
            {datum.amountLabel}
          </div>
        )}
      </div>
      <span
        className={`text-[10px] font-medium ${
          datum.isToday ? "font-bold" : "text-on-surface-variant/50"
        }`}
        style={datum.isToday ? { color: COLOR_PRIMARY } : undefined}
      >
        {datum.label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link SpendRangeToggle}. */
interface SpendRangeToggleProps {
  /** Currently active filter. */
  readonly activeFilter: SpendRangeFilter;
  /** Called when the user selects a different range. */
  readonly onFilterChange: (filter: SpendRangeFilter) => void;
}

/** Label text shown on each toggle pill. */
const FILTER_LABELS: Record<SpendRangeFilter, string> = {
  "7d": "Last 7 days",
  "30d": "30 days",
  all: "All time",
} as const satisfies Record<SpendRangeFilter, string>;

/** Ordered filter options for rendering the toggle. */
const FILTER_OPTIONS: readonly SpendRangeFilter[] = ["7d", "30d", "all"] as const;

/**
 * Pill-style toggle for selecting the spend chart's time range.
 *
 * @param props - {@link SpendRangeToggleProps}
 * @returns A rounded pill group with three selectable options.
 */
function SpendRangeToggle({ activeFilter, onFilterChange }: SpendRangeToggleProps): JSX.Element {
  return (
    <div className="flex bg-surface-container-low p-1 rounded-full">
      {FILTER_OPTIONS.map((filter) => {
        const isActive = filter === activeFilter;

        function handleClick(): void {
          onFilterChange(filter);
        }

        return (
          <button
            key={filter}
            onClick={handleClick}
            className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-colors ${
              isActive
                ? "bg-white shadow-sm"
                : "font-medium text-on-surface-variant hover:text-primary"
            }`}
            style={isActive ? { color: COLOR_PRIMARY } : undefined}
          >
            {FILTER_LABELS[filter]}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link DailySpendTrendCard}. */
interface DailySpendTrendCardProps {
  /** Currently active time range filter. */
  readonly activeFilter: SpendRangeFilter;
  /** Called when the user changes the time range. */
  readonly onFilterChange: (filter: SpendRangeFilter) => void;
}

/**
 * Full-width card containing the daily spend bar chart and range toggle.
 *
 * @param props - {@link DailySpendTrendCardProps}
 * @returns A white card with heading, toggle, and the bar chart.
 */
function DailySpendTrendCard({
  activeFilter,
  onFilterChange,
}: DailySpendTrendCardProps): JSX.Element {
  const bars = SPEND_BARS_BY_FILTER[activeFilter];

  return (
    <div
      className="bg-white p-11 rounded-xl"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <div className="flex justify-between items-start mb-10">
        <div>
          <h3 className="text-xl font-bold text-on-surface">Daily Spend Trend</h3>
          <p className="text-sm text-on-surface-variant mt-1">
            Aggregation of all pipeline costs across active models
          </p>
        </div>
        <SpendRangeToggle activeFilter={activeFilter} onFilterChange={onFilterChange} />
      </div>

      {/* Chart area */}
      <div className="h-64 flex items-end justify-between gap-4 px-4 border-b border-slate-100">
        {bars.map((datum) => (
          <SpendBar key={datum.label} datum={datum} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link StageProgressRow}. */
interface StageProgressRowProps {
  /** Cost data for this pipeline stage. */
  readonly spend: StageSpend;
}

/**
 * A single labeled horizontal progress bar row for one pipeline stage.
 *
 * @param props - {@link StageProgressRowProps}
 * @returns A label row + colored indigo progress bar.
 */
function StageProgressRow({ spend }: StageProgressRowProps): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs font-bold text-on-surface-variant tracking-wide">
        <span>{spend.stage}</span>
        <span>{spend.amount}</span>
      </div>
      <div className="h-2 w-full bg-slate-50 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${spend.barWidthPct}%`,
            backgroundColor: COLOR_PRIMARY,
          }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

/**
 * Card listing pipeline stage costs as labeled horizontal progress bars.
 *
 * @returns A white card with "Cost by Stage" heading and four stage rows.
 */
function CostByStageCard(): JSX.Element {
  return (
    <div
      className="bg-white p-11 rounded-xl"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <h3 className="text-xl font-bold text-on-surface mb-8">Cost by Stage</h3>
      <div className="space-y-6">
        {STAGE_COSTS.map((spend) => (
          <StageProgressRow key={spend.stage} spend={spend} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link RecentFailureRow}. */
interface RecentFailureRowProps {
  /** The failure record to display. */
  readonly failure: RecentFailure;
  /** Called when the user clicks the retry icon for this failure. */
  readonly onRetry: (id: number) => void;
}

/**
 * One row in the compact recent-failures table.
 *
 * @param props - {@link RecentFailureRowProps}
 * @returns A `<tr>` with stage badge, job title, error code, time, and retry.
 */
function RecentFailureRow({ failure, onRetry }: RecentFailureRowProps): JSX.Element {
  function handleRetryClick(): void {
    onRetry(failure.id);
  }

  return (
    <tr className="group hover:bg-slate-50/50 transition-colors">
      <td className="py-5">
        <span
          className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-tighter ${failure.stageBadgeClass}`}
        >
          {failure.stage}
        </span>
      </td>
      <td className="py-5">
        <p className="text-xs font-semibold text-on-surface">{failure.jobTitle}</p>
      </td>
      <td className="py-5">
        <code className="text-[10px] font-mono text-red-500 font-bold bg-red-50 px-1.5 py-0.5 rounded">
          {failure.errorCode}
        </code>
      </td>
      <td className="py-5">
        <p className="text-[10px] text-on-surface-variant font-medium">{failure.time}</p>
      </td>
      <td className="py-5 text-right">
        <button
          onClick={handleRetryClick}
          aria-label={`Retry ${failure.jobTitle}`}
          className="hover:opacity-70 transition-opacity"
          style={{ color: COLOR_PRIMARY }}
        >
          <span className="material-symbols-outlined text-lg">replay</span>
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------

/** Props for {@link RecentFailuresCard}. */
interface RecentFailuresCardProps {
  /** Called when the user clicks retry on a specific failure row. */
  readonly onRetry: (id: number) => void;
}

/**
 * Compact card table listing recent pipeline failures for quick triage.
 *
 * @param props - {@link RecentFailuresCardProps}
 * @returns A white card with a "Recent Failures" heading and a data table.
 */
function RecentFailuresCard({ onRetry }: RecentFailuresCardProps): JSX.Element {
  return (
    <div
      className="bg-white p-11 rounded-xl overflow-hidden"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <h3 className="text-xl font-bold text-on-surface mb-8">Recent Failures</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[10px] font-black text-on-surface-variant/40 uppercase tracking-widest border-b border-slate-50">
              <th className="pb-4">Stage</th>
              <th className="pb-4">Job Title</th>
              <th className="pb-4">Error</th>
              <th className="pb-4">Time</th>
              <th className="pb-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {RECENT_FAILURES.map((failure) => (
              <RecentFailureRow key={failure.id} failure={failure} onRetry={onRetry} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

/**
 * Cost Tracking page component.
 *
 * @remarks
 * Renders inside {@link AppLayout} via React Router `<Outlet />`. The outer
 * `<div>` provides the page-level padding and max-width; the shared sidebar
 * and topbar are owned by AppLayout.
 *
 * @returns The full Cost Tracking page content.
 */
export function CostTrackingPage(): JSX.Element {
  const [spendFilter, setSpendFilter] = useState<SpendRangeFilter>("7d");

  function handleFilterChange(filter: SpendRangeFilter): void {
    setSpendFilter(filter);
  }

  function handleRetry(id: number): void {
    console.info(`[CostTrackingPage] Retry requested for failure id=${id}`);
  }

  const totalSpendSubtitle = (
    <div className="flex items-center gap-2">
      <span className="font-bold text-green-600 flex items-center gap-0.5">
        <span className="material-symbols-outlined text-sm">trending_up</span>
        $3.12
      </span>
      <span className="text-on-surface-variant/60 font-medium">Calculated today vs yesterday</span>
    </div>
  );

  const avgCostSubtitle = (
    <span className="text-on-surface-variant/60 font-medium italic">
      Optimization target: &lt; $0.20
    </span>
  );

  const apiCallsSubtitle = (
    <span className="text-on-surface-variant/60 font-medium">89% of daily quota utilized</span>
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Row 1 — KPI stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <StatCard
          label="Total Spend"
          value={TOTAL_SPEND}
          icon="account_balance_wallet"
          subtitle={totalSpendSubtitle}
        />
        <StatCard
          label="Avg Cost Per App"
          value={AVG_COST_PER_APP}
          icon="analytics"
          subtitle={avgCostSubtitle}
        />
        <StatCard
          label="API Calls Today"
          value={String(API_CALLS_TODAY)}
          icon="auto_awesome"
          iconFilled
          subtitle={apiCallsSubtitle}
        />
      </div>

      {/* Row 2 — Daily spend trend chart */}
      <DailySpendTrendCard activeFilter={spendFilter} onFilterChange={handleFilterChange} />

      {/* Row 3 — Cost by Stage + Recent Failures (50 / 50) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <CostByStageCard />
        <RecentFailuresCard onRetry={handleRetry} />
      </div>
    </div>
  );
}
