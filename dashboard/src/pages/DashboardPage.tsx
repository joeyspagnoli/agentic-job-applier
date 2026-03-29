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
  COLOR_ERROR,
  COLOR_JOBSPY_SEGMENT,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_SECONDARY,
} from "@/lib/design-tokens";

/** Which trend range is active in the discovery chart. */
type TrendRange = "7d" | "30d";

/**
 * Resolve one stable color per source label for chart slices.
 *
 * @param source - Source label from backend DTO.
 * @returns Hex color string used by charts.
 */
function sourceColor(source: string): string {
  if (source === "GREENHOUSE") {
    return COLOR_PRIMARY;
  }
  if (source === "WORKDAY") {
    return COLOR_SECONDARY;
  }
  return COLOR_JOBSPY_SEGMENT;
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
    <div className="p-8 space-y-8">
      <div className="grid grid-cols-4 gap-6">
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
                  ? "#16a34a"
                  : "#64748b"
            }
            badge={card.label === "Awaiting Review" && Number.parseInt(card.value, 10) > 0 ? "URGENT" : undefined}
            loading={statsQuery.isLoading}
          />
        ))}
      </div>

      {(statsQuery.isError || trendQuery.isError) && (
        <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load dashboard data. Use Sync now to retry.
        </div>
      )}

      <div className="grid grid-cols-10 gap-6">
        <div className="col-span-6 bg-white rounded-xl p-6 ambient-shadow border border-white/40">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Discovery Trends
            </h3>
            <div className="flex items-center gap-2 rounded-full bg-slate-100 p-1">
              <RangeButton
                active={trendRange === "7d"}
                label="Last 7 days"
                onClick={() => {
                  setTrendRange("7d");
                }}
              />
              <RangeButton
                active={trendRange === "30d"}
                label="Last 30 days"
                onClick={() => {
                  setTrendRange("30d");
                }}
              />
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trendData}>
                <XAxis dataKey="day" tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 12 }} />
                <YAxis tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill={COLOR_PRIMARY} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="col-span-4 bg-white rounded-xl p-6 ambient-shadow border border-white/40">
          <h3 className="text-lg font-bold mb-4" style={{ color: COLOR_ON_SURFACE }}>
            Source Breakdown
          </h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={sourceBreakdown} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85}>
                  {sourceBreakdown.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-1 gap-2 mt-2">
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

      <div className="grid grid-cols-2 gap-6 pb-12">
        <div className="bg-white rounded-xl p-6 ambient-shadow border border-white/40">
          <h3 className="text-lg font-bold mb-6" style={{ color: COLOR_ON_SURFACE }}>
            Pipeline Funnel
          </h3>
          <div className="space-y-3">
            {pipelineData.map((row) => (
              <div key={row.stage} className="space-y-1">
                <div className="flex items-center justify-between text-xs font-medium">
                  <span style={{ color: COLOR_ON_SURFACE }}>{row.stage}</span>
                  <span style={{ color: COLOR_ON_SURFACE_VARIANT }}>{row.count.toLocaleString()}</span>
                </div>
                <div className="h-2 rounded-full" style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}33` }}>
                  <div
                    className="h-2 rounded-full"
                    style={{ width: `${row.widthPct}%`, backgroundColor: COLOR_PRIMARY }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl p-6 ambient-shadow border border-white/40">
          <h3 className="text-lg font-bold mb-4" style={{ color: COLOR_ON_SURFACE }}>
            Applications Over Time
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={applicationsOverTime}>
                <XAxis dataKey="label" tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 12 }} />
                <YAxis tick={{ fill: COLOR_ON_SURFACE_VARIANT, fontSize: 12 }} />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="tailored"
                  stroke={COLOR_SECONDARY}
                  fill={COLOR_SECONDARY}
                  fillOpacity={0.2}
                />
                <Area
                  type="monotone"
                  dataKey="applied"
                  stroke={COLOR_PRIMARY}
                  fill={COLOR_PRIMARY}
                  fillOpacity={0.2}
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
function StatCard({ label, value, subText, subTextColor, badge, loading }: StatCardProps): JSX.Element {
  return (
    <div className="bg-white p-6 rounded-xl ambient-shadow border border-white/40">
      <div className="flex justify-between items-start mb-2">
        <p className="text-[11px] font-bold uppercase tracking-widest" style={{ color: `${COLOR_ON_SURFACE_VARIANT}99` }}>
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
          {loading ? "--" : value}
        </span>
        <span className="text-xs font-bold" style={{ color: subTextColor }}>
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
      className="px-3 py-1.5 rounded-full text-xs font-semibold transition-colors"
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
