/**
 * @packageDocumentation
 *
 * Dashboard overview page for the AutoApply pipeline.
 */

import type { JSX } from "react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toDashboardKpis, toDiscoveryChartPoints } from "@/lib/api/adapters";
import { fetchDashboardStats, fetchDiscoveryTrend } from "@/lib/api/client";
import {
  COLOR_BLUSH,
  COLOR_ERROR,
  COLOR_JOBSPY_SEGMENT,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_SECONDARY,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_TERTIARY,
} from "@/lib/design-tokens";

/** Which trend range is active in the discovery chart. */
type TrendRange = "7d" | "30d";

/** Chart color palette for source breakdown. */
const SOURCE_COLORS: Record<string, string> = {
  GREENHOUSE: COLOR_PRIMARY,
  WORKDAY: COLOR_SECONDARY,
  JOBSPY: COLOR_JOBSPY_SEGMENT,
  adzuna: COLOR_TERTIARY,
  remotive: COLOR_BLUSH,
};

/**
 * Resolve one stable color per source label for chart slices.
 *
 * @param source - Source label from backend DTO.
 * @returns Hex color string used by charts.
 */
function sourceColor(source: string): string {
  return SOURCE_COLORS[source] ?? COLOR_OUTLINE;
}

/**
 * Dashboard overview page component.
 *
 * @returns The full dashboard page content element.
 */
export function DashboardPage(): JSX.Element {
  const [trendRange, setTrendRange] = useState<TrendRange>("7d");

  const statsQuery = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: fetchDashboardStats,
  });
  const trendQuery = useQuery({
    queryKey: ["dashboard", "discovery-trend", trendRange],
    queryFn: () => fetchDiscoveryTrend(trendRange),
  });

  const kpis = statsQuery.data ? toDashboardKpis(statsQuery.data) : [];
  const trendData = trendQuery.data ? toDiscoveryChartPoints(trendQuery.data) : [];
  const sourceBreakdown =
    statsQuery.data?.source_breakdown.map((item) => ({
      name: item.source,
      value: item.count,
      color: sourceColor(item.source),
    })) ?? [];
  const pipelineData =
    statsQuery.data?.pipeline_funnel.map((item) => ({
      stage: item.stage,
      count: item.count,
      widthPct:
        statsQuery.data.pipeline_funnel.length === 0
          ? 0
          : (item.count /
              Math.max(...statsQuery.data.pipeline_funnel.map((stageRow) => stageRow.count), 1)) *
            100,
    })) ?? [];
  const applicationsOverTime =
    statsQuery.data?.applications_over_time.map((item) => ({
      label: item.label,
      applied: item.applied,
      tailored: item.tailored,
    })) ?? [];

  return (
    <div className="p-8 space-y-8 max-w-[1400px] mx-auto">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        {kpis.map((card) => (
          <StatCard
            key={card.label}
            label={card.label}
            value={card.value}
            subText={card.subText}
            subTextColor={
              card.label === "Awaiting Review"
                ? COLOR_ERROR
                : card.subText.startsWith("+")
                  ? COLOR_TERTIARY
                  : COLOR_OUTLINE
            }
            badge={
              card.label === "Awaiting Review" && Number.parseInt(card.value, 10) > 0
                ? "URGENT"
                : undefined
            }
            loading={statsQuery.isLoading}
          />
        ))}
      </div>

      {/* Error banner */}
      {(statsQuery.isError || trendQuery.isError) && (
        <div className="rounded-xl border border-error-container bg-error-container px-4 py-3 text-sm text-on-error-container">
          Failed to load dashboard data. Use Sync now to retry.
        </div>
      )}

      {/* Charts row 1 */}
      <div className="grid grid-cols-10 gap-6">
        <div
          className="col-span-6 rounded-2xl p-6 ambient-shadow border"
          style={{ backgroundColor: "#ffffff", borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
        >
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-base font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Discovery Trends
            </h3>
            <div
              className="flex items-center gap-1 rounded-xl p-1"
              style={{ backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}
            >
              <RangeButton
                active={trendRange === "7d"}
                label="7 days"
                onClick={() => {
                  setTrendRange("7d");
                }}
              />
              <RangeButton
                active={trendRange === "30d"}
                label="30 days"
                onClick={() => {
                  setTrendRange("30d");
                }}
              />
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trendData}>
                <XAxis dataKey="day" tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 11 }} />
                <YAxis tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill={COLOR_PRIMARY} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div
          className="col-span-4 rounded-2xl p-6 ambient-shadow border"
          style={{ backgroundColor: "#ffffff", borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
        >
          <h3 className="text-base font-bold mb-4" style={{ color: COLOR_ON_SURFACE }}>
            Source Breakdown
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={sourceBreakdown}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={50}
                  outerRadius={80}
                >
                  {sourceBreakdown.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-1 gap-1.5 mt-2">
            {sourceBreakdown.map((entry) => (
              <div key={entry.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                  <span style={{ color: COLOR_ON_SURFACE }}>{entry.name}</span>
                </div>
                <span style={{ color: COLOR_ON_SURFACE_VARIANT }}>{entry.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-2 gap-6 pb-8">
        <div
          className="rounded-2xl p-6 ambient-shadow border"
          style={{ backgroundColor: "#ffffff", borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
        >
          <h3 className="text-base font-bold mb-5" style={{ color: COLOR_ON_SURFACE }}>
            Pipeline Funnel
          </h3>
          <div className="space-y-3">
            {pipelineData.map((row) => (
              <div key={row.stage} className="space-y-1">
                <div className="flex items-center justify-between text-xs font-medium">
                  <span style={{ color: COLOR_ON_SURFACE }}>{row.stage}</span>
                  <span style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    {row.count.toLocaleString()}
                  </span>
                </div>
                <div
                  className="h-2 rounded-full"
                  style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}30` }}
                >
                  <div
                    className="h-2 rounded-full transition-all duration-500"
                    style={{ width: `${row.widthPct}%`, backgroundColor: COLOR_PRIMARY }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          className="rounded-2xl p-6 ambient-shadow border"
          style={{ backgroundColor: "#ffffff", borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
        >
          <h3 className="text-base font-bold mb-4" style={{ color: COLOR_ON_SURFACE }}>
            Applications Over Time
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={applicationsOverTime}>
                <XAxis dataKey="label" tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 11 }} />
                <YAxis tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 11 }} />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="tailored"
                  stroke={COLOR_SECONDARY}
                  fill={COLOR_SECONDARY}
                  fillOpacity={0.15}
                />
                <Area
                  type="monotone"
                  dataKey="applied"
                  stroke={COLOR_PRIMARY}
                  fill={COLOR_PRIMARY}
                  fillOpacity={0.15}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Props for the dashboard stat card component. */
interface StatCardProps {
  /** Card label. */
  readonly label: string;
  /** Main card value. */
  readonly value: string;
  /** Small status text under value. */
  readonly subText: string;
  /** CSS color for subtext. */
  readonly subTextColor: string;
  /** Optional urgency badge. */
  readonly badge?: string;
  /** Loading flag for skeleton text. */
  readonly loading: boolean;
}

/**
 * Render one KPI stat card on the dashboard.
 *
 * @param props - {@link StatCardProps}
 * @returns One dashboard KPI card.
 */
function StatCard({
  label,
  value,
  subText,
  subTextColor,
  badge,
  loading,
}: StatCardProps): JSX.Element {
  return (
    <div
      className="p-5 rounded-2xl ambient-shadow border"
      style={{ backgroundColor: "#ffffff", borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
    >
      <div className="flex justify-between items-start mb-2">
        <p
          className="text-[10px] font-bold uppercase tracking-widest"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
        >
          {label}
        </p>
        {badge !== undefined && (
          <span className="bg-error-container text-on-error-container text-[9px] px-2 py-0.5 rounded-lg font-bold">
            {badge}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span
          className="text-fluid-2xl font-extrabold tracking-tight"
          style={{ color: COLOR_ON_SURFACE }}
        >
          {loading ? "--" : value}
        </span>
        <span className="text-xs font-semibold" style={{ color: subTextColor }}>
          {loading ? "Loading..." : subText}
        </span>
      </div>
    </div>
  );
}

/** Props for range toggle buttons in chart controls. */
interface RangeButtonProps {
  /** Active visual state. */
  readonly active: boolean;
  /** Button text. */
  readonly label: string;
  /** Click callback. */
  readonly onClick: () => void;
}

/**
 * Render one dashboard chart range toggle button.
 *
 * @param props - {@link RangeButtonProps}
 * @returns One range toggle button element.
 */
function RangeButton({ active, label, onClick }: RangeButtonProps): JSX.Element {
  return (
    <button
      className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
      style={{
        backgroundColor: active ? COLOR_PRIMARY : "transparent",
        color: active ? "#ffffff" : COLOR_ON_SURFACE_VARIANT,
      }}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
