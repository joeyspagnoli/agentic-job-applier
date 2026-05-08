/**
 * @packageDocumentation
 *
 * Cost Tracking page wired to live cost and failures endpoints.
 */

import type { JSX } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  formatUsd,
  toCostByStageRows,
  toCostDailyTrendPoints,
  toCostKpis,
  toFailuresModel,
} from "@/lib/api/adapters";
import {
  fetchCostByStage,
  fetchCostDailyTrend,
  fetchCostStats,
  fetchBudget,
  fetchFailures,
  retryFailure,
} from "@/lib/api/client";
import {
  COLOR_ERROR,
  COLOR_ERROR_CONTAINER,
  COLOR_ON_ERROR_CONTAINER,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_CONTAINER,
} from "@/lib/design-tokens";

/** Supported chart filter values for spend trend. */
type SpendRangeFilter = "7d" | "30d" | "all";

const RECENT_FAILURES_PAGE_SIZE = 5;

/**
 * Resolve badge style classes for failure stage labels.
 *
 * @param stage - Failure stage label from API.
 * @returns Tailwind class string.
 */
function failureStageClass(stage: string): string {
  if (stage === "TAILORING") {
    return "bg-warning-container text-on-warning-container";
  }
  if (stage === "REVIEW") {
    return "bg-primary-fixed text-primary";
  }
  if (stage === "APPLY") {
    return "bg-rose-100 text-rose-700";
  }
  if (stage === "GATE") {
    return "bg-surface-container-high text-on-surface-variant";
  }
  return "bg-surface-container text-on-surface-variant";
}

/**
 * Convert API timestamp into a short local label.
 *
 * @param rawValue - Raw timestamp from API.
 * @returns Localized timestamp string.
 */
function formatFailureTime(rawValue: string): string {
  const parsedDate = new Date(rawValue);
  if (Number.isNaN(parsedDate.valueOf())) {
    return rawValue;
  }
  return parsedDate.toLocaleString();
}

/**
 * Cost Tracking page component.
 *
 * @returns Full cost analytics page with live backend data.
 */
export function CostTrackingPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [spendFilter, setSpendFilter] = useState<SpendRangeFilter>("7d");

  const statsQuery = useQuery({
    queryKey: ["costs", "stats"],
    queryFn: fetchCostStats,
  });

  const trendQuery = useQuery({
    queryKey: ["costs", "daily-trend", spendFilter],
    queryFn: () => fetchCostDailyTrend(spendFilter),
  });
  const budgetQuery = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
  });

  const stageQuery = useQuery({
    queryKey: ["costs", "by-stage"],
    queryFn: fetchCostByStage,
  });

  const recentFailuresQuery = useQuery({
    queryKey: ["failures", "recent-for-cost"],
    queryFn: async () =>
      toFailuresModel(
        await fetchFailures({
          search: "",
          stage: "",
          status: "",
          page: 1,
          pageSize: RECENT_FAILURES_PAGE_SIZE,
        }),
      ),
  });

  const retryMutation = useMutation({
    mutationFn: retryFailure,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["failures"] });
      await queryClient.invalidateQueries({ queryKey: ["costs"] });
    },
  });

  const kpis = statsQuery.data
    ? toCostKpis(statsQuery.data)
    : {
        totalSpend: "$0.00",
        avgCostPerApp: "$0.00",
        apiCallsToday: "0",
      };

  const trendBars = useMemo(() => {
    const points = trendQuery.data ? toCostDailyTrendPoints(trendQuery.data) : [];
    const maxSpend = Math.max(0, ...points.map((point) => point.spendUsd));

    return points.map((point, index) => ({
      label: point.label,
      spendUsd: point.spendUsd,
      heightPct: maxSpend === 0 ? 0 : (point.spendUsd / maxSpend) * 100,
      isLatest: index === points.length - 1,
    }));
  }, [trendQuery.data]);

  const stageRows = useMemo(
    () => (stageQuery.data ? toCostByStageRows(stageQuery.data) : []),
    [stageQuery.data],
  );

  const recentFailures = recentFailuresQuery.data?.items ?? [];
  const isBudgetExceeded =
    budgetQuery.data !== undefined &&
    (budgetQuery.data.remaining_usd <= 0 || budgetQuery.data.utilization_pct >= 100);
  const hasError =
    statsQuery.isError ||
    trendQuery.isError ||
    stageQuery.isError ||
    recentFailuresQuery.isError ||
    retryMutation.isError;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {isBudgetExceeded && (
        <div
          className="rounded-xl border px-4 py-3 text-sm font-semibold"
          style={{
            color: COLOR_ON_ERROR_CONTAINER,
            backgroundColor: COLOR_ERROR_CONTAINER,
            borderColor: `${COLOR_ERROR}55`,
          }}
        >
          Monthly budget exceeded — pipeline paused
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <StatCard
          label="Total Spend"
          value={kpis.totalSpend}
          icon="account_balance_wallet"
          subtitle={
            <span className="text-outline font-medium">Current month total across all stages</span>
          }
        />
        <StatCard
          label="Avg Cost Per App"
          value={kpis.avgCostPerApp}
          icon="analytics"
          subtitle={
            <span className="text-slate-500 font-medium">Based on approved applications</span>
          }
        />
        <StatCard
          label="API Calls Today"
          value={kpis.apiCallsToday}
          icon="auto_awesome"
          iconFilled
          subtitle={<span className="text-slate-500 font-medium">Recorded cost events today</span>}
        />
      </div>

      {hasError && (
        <div className="rounded-xl border border-error-container bg-error-container px-4 py-3 text-sm text-on-error-container">
          Failed to load or mutate cost data. Use Sync now to retry.
        </div>
      )}

      <DailySpendTrendCard
        bars={trendBars}
        activeFilter={spendFilter}
        onFilterChange={(filter) => {
          setSpendFilter(filter);
        }}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <CostByStageCard stageRows={stageRows} />
        <RecentFailuresCard
          rows={recentFailures}
          pendingRetryId={retryMutation.isPending ? retryMutation.variables : null}
          onRetry={(failureId) => {
            retryMutation.mutate(failureId);
          }}
        />
      </div>
    </div>
  );
}

/** Props for KPI cards. */
interface StatCardProps {
  /** Card heading text. */
  readonly label: string;
  /** Primary card metric. */
  readonly value: string;
  /** Material icon name. */
  readonly icon: string;
  /** Optional filled icon style flag. */
  readonly iconFilled?: boolean;
  /** Subtitle element. */
  readonly subtitle: JSX.Element;
}

/**
 * Render one KPI stat card.
 *
 * @param props - Card display props.
 * @returns Card element.
 */
function StatCard({
  label,
  value,
  icon,
  iconFilled = false,
  subtitle,
}: StatCardProps): JSX.Element {
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
            ...(iconFilled ? { fontVariationSettings: "'FILL' 1" } : {}),
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

/** Props for spend trend card. */
interface DailySpendTrendCardProps {
  /** Trend bar data. */
  readonly bars: readonly {
    readonly label: string;
    readonly spendUsd: number;
    readonly heightPct: number;
    readonly isLatest: boolean;
  }[];
  /** Active range filter. */
  readonly activeFilter: SpendRangeFilter;
  /** Range-change callback. */
  readonly onFilterChange: (filter: SpendRangeFilter) => void;
}

const SPEND_FILTER_LABELS: Record<SpendRangeFilter, string> = {
  "7d": "Last 7 days",
  "30d": "30 days",
  all: "All time",
};

/**
 * Render the spend trend chart and range toggle.
 *
 * @param props - Spend chart props.
 * @returns Trend card element.
 */
function DailySpendTrendCard({
  bars,
  activeFilter,
  onFilterChange,
}: DailySpendTrendCardProps): JSX.Element {
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

        <div className="flex bg-surface-container-low p-1 rounded-full">
          {(["7d", "30d", "all"] as const).map((filterKey) => {
            const isActive = filterKey === activeFilter;
            return (
              <button
                key={filterKey}
                className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-colors ${
                  isActive
                    ? "bg-white shadow-sm"
                    : "font-medium text-on-surface-variant hover:text-primary"
                }`}
                style={isActive ? { color: COLOR_PRIMARY } : undefined}
                onClick={() => {
                  onFilterChange(filterKey);
                }}
              >
                {SPEND_FILTER_LABELS[filterKey]}
              </button>
            );
          })}
        </div>
      </div>

      <div
        className={`h-64 flex items-end justify-between px-4 border-b border-outline-variant/30 overflow-x-auto ${
          bars.length > 14 ? "gap-1" : "gap-4"
        }`}
      >
        {bars.map((bar) => (
          <div
            key={`${bar.label}-${bar.spendUsd}`}
            className="flex-1 flex flex-col items-center gap-2 group"
          >
            <div
              className="w-full rounded-t-lg transition-all relative"
              style={{
                backgroundColor: bar.isLatest ? COLOR_PRIMARY : `${COLOR_PRIMARY}1A`,
                height: `${bar.heightPct}%`,
                minHeight: bar.heightPct === 0 ? "6px" : undefined,
              }}
            >
              <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-on-surface text-white px-2 py-1 rounded text-[10px] font-bold opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                {formatUsd(bar.spendUsd)}
              </div>
            </div>
            <span
              className={`text-[10px] font-medium ${bar.isLatest ? "font-bold" : "text-on-surface-variant/50"}`}
              style={bar.isLatest ? { color: COLOR_PRIMARY } : undefined}
            >
              {bar.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Props for cost-by-stage card. */
interface CostByStageCardProps {
  /** Stage rows with computed widths. */
  readonly stageRows: readonly {
    readonly stage: string;
    readonly spendUsd: number;
    readonly widthPct: number;
  }[];
}

/**
 * Render cost-by-stage horizontal bars.
 *
 * @param props - Stage cost props.
 * @returns Stage costs card.
 */
function CostByStageCard({ stageRows }: CostByStageCardProps): JSX.Element {
  return (
    <div
      className="bg-white p-11 rounded-xl"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <h3 className="text-xl font-bold text-on-surface mb-8">Cost by Stage</h3>
      <div className="space-y-6">
        {stageRows.length === 0 && (
          <p className="text-sm text-outline">No stage cost data has been recorded yet.</p>
        )}
        {stageRows.map((row) => (
          <div key={row.stage} className="space-y-2">
            <div className="flex justify-between text-xs font-bold text-on-surface-variant tracking-wide">
              <span>{row.stage}</span>
              <span>{formatUsd(row.spendUsd)}</span>
            </div>
            <div className="h-2 w-full bg-surface-container-low rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${row.widthPct}%`, backgroundColor: COLOR_PRIMARY }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Props for recent failures card. */
interface RecentFailuresCardProps {
  /** Recent failure records. */
  readonly rows: readonly {
    readonly id: string;
    readonly stage: string;
    readonly position: string;
    readonly error_code: string;
    readonly time: string;
  }[];
  /** Failure ID currently being retried. */
  readonly pendingRetryId: string | null;
  /** Retry callback. */
  readonly onRetry: (failureId: string) => void;
}

/**
 * Render recent failures table with retry actions.
 *
 * @param props - Recent failures props.
 * @returns Recent failures card.
 */
function RecentFailuresCard({
  rows,
  pendingRetryId,
  onRetry,
}: RecentFailuresCardProps): JSX.Element {
  return (
    <div
      className="bg-white p-11 rounded-xl overflow-hidden"
      style={{ boxShadow: "0 12px 32px -4px rgba(70,72,212,0.06)" }}
    >
      <h3 className="text-xl font-bold text-on-surface mb-8">Recent Failures</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[10px] font-black text-on-surface-variant/40 uppercase tracking-widest border-b border-outline-variant/20">
              <th className="pb-4">Stage</th>
              <th className="pb-4">Job Title</th>
              <th className="pb-4">Error</th>
              <th className="pb-4">Time</th>
              <th className="pb-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/20">
            {rows.map((row) => (
              <tr
                key={row.id}
                className="group hover:bg-surface-container-low/50 transition-colors"
              >
                <td className="py-5">
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-tighter ${failureStageClass(row.stage)}`}
                  >
                    {row.stage}
                  </span>
                </td>
                <td className="py-5">
                  <p className="text-xs font-semibold text-on-surface">{row.position}</p>
                </td>
                <td className="py-5">
                  <code className="text-[10px] font-mono text-error font-bold bg-error-container px-1.5 py-0.5 rounded">
                    {row.error_code}
                  </code>
                </td>
                <td className="py-5">
                  <p className="text-[10px] text-on-surface-variant font-medium">
                    {formatFailureTime(row.time)}
                  </p>
                </td>
                <td className="py-5 text-right">
                  <button
                    onClick={() => {
                      onRetry(row.id);
                    }}
                    disabled={pendingRetryId === row.id}
                    aria-label={`Retry ${row.position}`}
                    className="hover:opacity-70 transition-opacity disabled:opacity-50"
                    style={{ color: COLOR_PRIMARY }}
                  >
                    <span className="material-symbols-outlined text-lg">
                      {pendingRetryId === row.id ? "hourglass_top" : "replay"}
                    </span>
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-sm text-outline">
                  No recent failures.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        Showing up to {RECENT_FAILURES_PAGE_SIZE} most recent failure records.
      </p>
    </div>
  );
}
