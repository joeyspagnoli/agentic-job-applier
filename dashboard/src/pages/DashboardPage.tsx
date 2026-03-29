/**
 * @packageDocumentation
 *
 * Dashboard overview page for the AutoApply pipeline.
 *
 * @remarks
 * Displays four KPI stat cards and four chart sections:
 * Discovery Trends (bar), Source Breakdown (donut), Pipeline Funnel
 * (horizontal bars), and Applications Over Time (area chart).
 *
 * All data is currently hardcoded mock values that match the Stitch design
 * mockup. Replace each constant with an API call once the FastAPI backend
 * is wired up.
 */

import type { JSX } from "react";
import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Area,
  AreaChart,
} from "recharts";
import {
  COLOR_PRIMARY,
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_SECONDARY,
  COLOR_JOBSPY_SEGMENT,
  COLOR_OUTLINE_VARIANT,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Mock data — replace with API calls when the FastAPI backend is wired up.
// ---------------------------------------------------------------------------

/** Discovery count by day of week for the "Last 7 days" toggle state. */
const DISCOVERY_LAST_7_DAYS = [
  { day: "Mon", count: 320 },
  { day: "Tue", count: 460 },
  { day: "Wed", count: 640 },
  { day: "Thu", count: 390 },
  { day: "Fri", count: 530 },
  { day: "Sat", count: 250 },
  { day: "Sun", count: 280 },
] as const;

/** Discovery count by week for the "Last 30 days" toggle state. */
const DISCOVERY_LAST_30_DAYS = [
  { day: "W1", count: 1200 },
  { day: "W2", count: 980 },
  { day: "W3", count: 1450 },
  { day: "W4", count: 1600 },
] as const;

/** Job source breakdown for the donut chart — percentages must sum to 100. */
const SOURCE_BREAKDOWN = [
  { name: "Greenhouse", value: 40, color: COLOR_PRIMARY },
  { name: "Workday", value: 32, color: COLOR_SECONDARY },
  { name: "JobSpy", value: 28, color: COLOR_JOBSPY_SEGMENT },
] as const;

/** Pipeline stage counts used to render the horizontal funnel bars. */
const PIPELINE_FUNNEL = [
  {
    stage: "Discovered",
    value: 2847,
    bgClass: "bg-amber-100",
    textClass: "text-amber-900",
    indentPx: 0,
  },
  {
    stage: "Qualified",
    value: 847,
    bgClass: "bg-indigo-100",
    textClass: "text-indigo-700",
    indentPx: 20,
  },
  {
    stage: "Tailored",
    value: 342,
    bgClass: "bg-indigo-200",
    textClass: "text-indigo-700",
    indentPx: 40,
  },
  {
    stage: "Applied",
    value: 198,
    bgClass: "bg-indigo-300",
    textClass: "text-indigo-800",
    indentPx: 60,
  },
  {
    stage: "Human Review",
    value: 12,
    bgClass: "bg-amber-200",
    textClass: "text-amber-700",
    indentPx: 80,
  },
] as const;

/** Hourly applied vs tailored counts for the Applications Over Time area chart. */
const APPLICATIONS_OVER_TIME = [
  { time: "12 AM", applied: 5, tailored: 12 },
  { time: "3 AM", applied: 8, tailored: 18 },
  { time: "6 AM", applied: 15, tailored: 25 },
  { time: "9 AM", applied: 22, tailored: 35 },
  { time: "12 PM", applied: 45, tailored: 60 },
  { time: "3 PM", applied: 38, tailored: 50 },
  { time: "6 PM", applied: 62, tailored: 72 },
  { time: "9 PM", applied: 80, tailored: 85 },
  { time: "NOW", applied: 95, tailored: 90 },
] as const;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Props for the {@link StatCard} component. */
interface StatCardProps {
  /** Uppercase label shown above the primary value. */
  readonly label: string;
  /** Large primary value string (e.g. "2,847"). */
  readonly value: string;
  /** Smaller secondary line shown below the value. */
  readonly subText: string;
  /**
   * Tailwind text color class applied to the sub-text.
   *
   * @defaultValue `"text-green-600"`
   */
  readonly subTextColorClass?: string;
  /** Optional badge label shown in the top-right corner of the card. */
  readonly badge?: string;
}

/**
 * KPI summary card used in the top row of the dashboard.
 *
 * @param props - {@link StatCardProps}
 * @returns A white rounded card element with a label, value, and optional badge.
 */
function StatCard({
  label,
  value,
  subText,
  subTextColorClass = "text-green-600",
  badge,
}: StatCardProps): JSX.Element {
  return (
    <div className="bg-white p-6 rounded-xl ambient-shadow border border-white/40">
      <div className="flex justify-between items-start mb-2">
        <p
          className="text-[11px] font-bold uppercase tracking-widest"
          style={{ color: `${COLOR_ON_SURFACE_VARIANT}99` }}
        >
          {label}
        </p>
        {badge !== undefined && (
          <span className="bg-[#ffdad6] text-[#93000a] text-[9px] px-2 py-0.5 rounded-full font-bold">
            {badge}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-black tracking-tight" style={{ color: COLOR_ON_SURFACE }}>
          {value}
        </span>
        <span className={`text-xs font-bold ${subTextColorClass}`}>{subText}</span>
      </div>
    </div>
  );
}

/** Which time range toggle is active on the Discovery Trends chart. */
type TrendRange = "7d" | "30d";

/**
 * Dashboard overview page component.
 *
 * @remarks
 * Renders four stat cards, the Discovery Trends bar chart with a time-range
 * toggle, the Source Breakdown donut chart, the Pipeline Funnel horizontal
 * bar chart, and the Applications Over Time area chart.
 *
 * @returns The full dashboard page content element.
 */
export function DashboardPage(): JSX.Element {
  const [trendRange, setTrendRange] = useState<TrendRange>("7d");
  const trendData = trendRange === "7d" ? DISCOVERY_LAST_7_DAYS : DISCOVERY_LAST_30_DAYS;

  return (
    <div className="p-8 space-y-8">
      {/* Row 1 — KPI stat cards */}
      <div className="grid grid-cols-4 gap-6">
        <StatCard label="Jobs Discovered" value="2,847" subText="+124 today" />
        <StatCard label="Resumes Tailored" value="342" subText="+18 today" />
        <StatCard label="Applications Sent" value="198" subText="+5 today" />
        <StatCard
          label="Awaiting Review"
          value="12"
          subText="Action required"
          subTextColorClass={`text-[${COLOR_ERROR}]`}
          badge="URGENT"
        />
      </div>

      {/* Row 2 — Discovery Trends (60%) + Source Breakdown (40%) */}
      <div className="grid grid-cols-10 gap-6">
        <DiscoveryTrendsCard
          data={[...trendData]}
          range={trendRange}
          onRangeChange={setTrendRange}
        />
        <SourceBreakdownCard />
      </div>

      {/* Row 3 — Pipeline Funnel (50%) + Applications Over Time (50%) */}
      <div className="grid grid-cols-2 gap-6 pb-12">
        <PipelineFunnelCard />
        <ApplicationsOverTimeCard />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart sub-components
// ---------------------------------------------------------------------------

/** Props for {@link DiscoveryTrendsCard}. */
interface DiscoveryTrendsCardProps {
  /** Bar chart data entries with a `day` label and `count` value. */
  readonly data: ReadonlyArray<{ readonly day: string; readonly count: number }>;
  /** Currently selected time range. */
  readonly range: TrendRange;
  /** Callback to update the selected time range. */
  readonly onRangeChange: (range: TrendRange) => void;
}

/**
 * Bar chart showing job discovery counts over the selected time range.
 *
 * @param props - {@link DiscoveryTrendsCardProps}
 * @returns A white card with toggle buttons and a Recharts BarChart.
 */
function DiscoveryTrendsCard({
  data,
  range,
  onRangeChange,
}: DiscoveryTrendsCardProps): JSX.Element {
  return (
    <div className="col-span-6 bg-white p-8 rounded-xl ambient-shadow">
      <div className="flex justify-between items-center mb-10">
        <h3 className="font-semibold text-lg" style={{ color: COLOR_ON_SURFACE }}>
          Discovery Trends
        </h3>
        <div className="bg-[#f3f4f5] p-1 rounded-full flex gap-1">
          <RangeToggleButton
            label="Last 7 days"
            isActive={range === "7d"}
            onClick={() => {
              onRangeChange("7d");
            }}
          />
          <RangeToggleButton
            label="Last 30 days"
            isActive={range === "30d"}
            onClick={() => {
              onRangeChange("30d");
            }}
          />
        </div>
      </div>
      <ResponsiveContainer width="100%" height={192}>
        <BarChart data={data} barSize={28}>
          <XAxis
            dataKey="day"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 10, fontWeight: 700, fill: COLOR_ON_SURFACE_VARIANT }}
          />
          <YAxis hide />
          <Tooltip
            cursor={{ fill: `${COLOR_PRIMARY}10` }}
            contentStyle={{
              borderRadius: 8,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
              fontSize: 12,
            }}
          />
          <Bar dataKey="count" fill={COLOR_PRIMARY} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Props for the {@link RangeToggleButton} button. */
interface RangeToggleButtonProps {
  /** Display label for the button. */
  readonly label: string;
  /** Whether this toggle is currently selected. */
  readonly isActive: boolean;
  /** Click handler. */
  readonly onClick: () => void;
}

/**
 * Pill-style toggle button used in the Discovery Trends time range selector.
 *
 * @param props - {@link RangeToggleButtonProps}
 * @returns A `<button>` styled as an active or inactive pill.
 */
function RangeToggleButton({ label, isActive, onClick }: RangeToggleButtonProps): JSX.Element {
  return (
    <button
      className={`text-xs font-bold px-4 py-1.5 rounded-full transition-colors ${
        isActive ? "bg-white shadow-sm" : "hover:text-[#191c1d]"
      }`}
      style={{ color: isActive ? COLOR_PRIMARY : `${COLOR_ON_SURFACE_VARIANT}99` }}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/**
 * Donut chart showing the percentage split between the three job sources.
 *
 * @returns A white card with a Recharts PieChart and a legend.
 */
function SourceBreakdownCard(): JSX.Element {
  return (
    <div className="col-span-4 bg-white p-8 rounded-xl ambient-shadow flex flex-col">
      <h3 className="font-semibold text-lg mb-8" style={{ color: COLOR_ON_SURFACE }}>
        Source Breakdown
      </h3>
      <div className="flex items-center gap-8 flex-1">
        {/* Donut */}
        <div className="relative" style={{ width: 160, height: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={[...SOURCE_BREAKDOWN]}
                cx="50%"
                cy="50%"
                innerRadius={52}
                outerRadius={72}
                dataKey="value"
                strokeWidth={0}
              >
                {SOURCE_BREAKDOWN.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {/* Center label — absolutely positioned over the donut hole */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-2xl font-black" style={{ color: COLOR_ON_SURFACE }}>
              3
            </span>
            <span
              className="text-[8px] font-black tracking-widest uppercase"
              style={{ color: `${COLOR_ON_SURFACE_VARIANT}80` }}
            >
              SOURCES
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="space-y-4">
          {SOURCE_BREAKDOWN.map((source) => (
            <div key={source.name} className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: source.color }} />
              <div className="flex flex-col">
                <span className="text-xs font-bold" style={{ color: COLOR_ON_SURFACE }}>
                  {source.name}
                </span>
                <span className="text-[10px]" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  {source.value}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Horizontal funnel chart showing how many jobs pass through each pipeline stage.
 *
 * @returns A white card with indented horizontal bar rows.
 */
function PipelineFunnelCard(): JSX.Element {
  return (
    <div className="bg-white p-8 rounded-xl ambient-shadow">
      <h3 className="font-semibold text-lg mb-8" style={{ color: COLOR_ON_SURFACE }}>
        Pipeline Funnel
      </h3>
      <div className="space-y-4">
        {PIPELINE_FUNNEL.map((row) => (
          <div key={row.stage} className="flex items-center gap-4">
            <div
              className="w-24 text-[10px] font-black uppercase"
              style={{ color: `${COLOR_ON_SURFACE_VARIANT}B3` }}
            >
              {row.stage}
            </div>
            <div
              className={`flex-1 h-10 ${row.bgClass} rounded-lg flex items-center px-4`}
              style={{ marginLeft: row.indentPx }}
            >
              <span className={`text-xs font-bold ${row.textClass}`}>
                {row.value.toLocaleString()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Dual-line area chart showing applied vs tailored counts over the current day.
 *
 * @returns A white card with a Recharts AreaChart and a legend.
 */
function ApplicationsOverTimeCard(): JSX.Element {
  return (
    <div className="bg-white p-8 rounded-xl ambient-shadow">
      <div className="flex justify-between items-center mb-8">
        <h3 className="font-semibold text-lg" style={{ color: COLOR_ON_SURFACE }}>
          Applications Over Time
        </h3>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLOR_PRIMARY }} />
            <span
              className="text-[10px] font-bold uppercase"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Applied
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-slate-300" />
            <span
              className="text-[10px] font-bold uppercase"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Tailored
            </span>
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={192}>
        <AreaChart data={[...APPLICATIONS_OVER_TIME]}>
          <defs>
            <linearGradient id="appliedAreaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={COLOR_PRIMARY} stopOpacity={0.15} />
              <stop offset="95%" stopColor={COLOR_PRIMARY} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 10, fontWeight: 700, fill: `${COLOR_ON_SURFACE_VARIANT}80` }}
          />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
              fontSize: 12,
            }}
          />
          {/* Tailored line — rendered first so Applied renders on top */}
          <Area type="monotone" dataKey="tailored" stroke="#cbd5e1" strokeWidth={2} fill="none" />
          <Area
            type="monotone"
            dataKey="applied"
            stroke={COLOR_PRIMARY}
            strokeWidth={3}
            fill="url(#appliedAreaGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
