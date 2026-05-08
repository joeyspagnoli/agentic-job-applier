/**
 * @packageDocumentation
 *
 * Failures page with live stage-failure data and retry actions.
 */

import type { ChangeEvent, JSX } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toFailuresModel } from "@/lib/api/adapters";
import { fetchFailures, retryFailure } from "@/lib/api/client";
import { COLOR_OUTLINE_VARIANT, COLOR_PRIMARY } from "@/lib/design-tokens";

const PAGE_SIZE = 20;

/**
 * Resolve badge styles for failure stage labels.
 *
 * @param stage - Failure stage label.
 * @returns Tailwind class list for badge rendering.
 */
function stageClass(stage: string): string {
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
 * Resolve status styles for retry state labels.
 *
 * @param status - Failure retry status.
 * @returns Tailwind class list.
 */
function statusClass(status: string): string {
  if (status === "RETRYING") {
    return "bg-emerald-100 text-emerald-700";
  }
  if (status === "EXHAUSTED") {
    return "bg-error-container text-on-error-container";
  }
  return "bg-surface-container text-on-surface-variant";
}

/**
 * Failures page root component.
 *
 * @returns The full failures page content.
 */
export function FailuresPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [stageFilter, setStageFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  const failuresQuery = useQuery({
    queryKey: [
      "failures",
      {
        search: searchQuery,
        stage: stageFilter,
        status: statusFilter,
        page: currentPage,
        pageSize: PAGE_SIZE,
      },
    ],
    queryFn: async () =>
      toFailuresModel(
        await fetchFailures({
          search: searchQuery,
          stage: stageFilter,
          status: statusFilter,
          page: currentPage,
          pageSize: PAGE_SIZE,
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

  const rows = failuresQuery.data?.items ?? [];
  const summary = failuresQuery.data?.summary;
  const totalPages = failuresQuery.data?.total_pages ?? 1;

  function handleSearchChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
    setCurrentPage(1);
  }

  function handleStageChange(event: ChangeEvent<HTMLSelectElement>): void {
    setStageFilter(event.target.value);
    setCurrentPage(1);
  }

  function handleStatusChange(event: ChangeEvent<HTMLSelectElement>): void {
    setStatusFilter(event.target.value);
    setCurrentPage(1);
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <SummaryCard
          label="Total Failures"
          value={String(summary?.total_failures ?? 0)}
          subtitle="Across all stages"
        />
        <SummaryCard
          label="Last 24 Hours"
          value={String(summary?.last_24_hours ?? 0)}
          subtitle="Recent failures"
        />
        <SummaryCard
          label="Most Failing Stage"
          value={summary?.most_failing_stage.stage ?? "NONE"}
          subtitle={`${summary?.most_failing_stage.count ?? 0} records`}
        />
        <SummaryCard
          label="Retry Success Rate"
          value={`${Math.round(summary?.retry_success_rate_pct ?? 0)}%`}
          subtitle="Estimated from active failures"
        />
      </div>

      <div className="bg-white p-4 rounded-xl border border-white flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="relative md:w-[420px]">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline">
            search
          </span>
          <input
            className="w-full rounded-lg border border-outline-variant bg-surface-container-low py-2 pl-10 pr-3 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            placeholder="Search failures..."
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </div>

        <div className="flex gap-3">
          <select
            className="rounded-lg border bg-white px-3 py-2 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            value={stageFilter}
            onChange={handleStageChange}
          >
            <option value="">All Stages</option>
            <option value="GATE">GATE</option>
            <option value="TAILORING">TAILORING</option>
            <option value="REVIEW">REVIEW</option>
            <option value="APPLY">APPLY</option>
          </select>

          <select
            className="rounded-lg border bg-white px-3 py-2 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            value={statusFilter}
            onChange={handleStatusChange}
          >
            <option value="">All Statuses</option>
            <option value="RETRYING">RETRYING</option>
            <option value="EXHAUSTED">EXHAUSTED</option>
          </select>
        </div>
      </div>

      {failuresQuery.isError && (
        <div className="rounded-xl border border-error-container bg-error-container px-4 py-3 text-sm text-on-error-container">
          Failed to load failures data. Use Sync now to retry.
        </div>
      )}

      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-low">
              {[
                "Stage",
                "Company",
                "Position",
                "Error",
                "Attempts",
                "Status",
                "Time",
                "Actions",
              ].map((column) => (
                <th
                  key={column}
                  className={`px-6 py-4 text-[10px] font-bold tracking-widest uppercase ${column === "Actions" ? "text-right" : ""}`}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <FailureRow
                key={row.id}
                row={row}
                expanded={expandedRow === row.id}
                pendingRetry={retryMutation.isPending && retryMutation.variables === row.id}
                onToggle={() => {
                  setExpandedRow((previous) => (previous === row.id ? null : row.id));
                }}
                onRetry={() => {
                  retryMutation.mutate(row.id);
                }}
              />
            ))}
            {failuresQuery.isLoading && (
              <tr>
                <td className="px-6 py-10 text-sm text-outline" colSpan={8}>
                  Loading failures...
                </td>
              </tr>
            )}
            {!failuresQuery.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-6 py-10 text-sm text-outline" colSpan={8}>
                  No failures match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={failuresQuery.data?.total_items ?? 0}
          onPageChange={(page) => {
            setCurrentPage(page);
            setExpandedRow(null);
          }}
        />
      </div>
    </div>
  );
}

/** Props for top summary cards. */
interface SummaryCardProps {
  /** Card label text. */
  readonly label: string;
  /** Card value text. */
  readonly value: string;
  /** Card subtitle text. */
  readonly subtitle: string;
}

/**
 * Render one summary card in the failures top row.
 *
 * @param props - {@link SummaryCardProps}
 * @returns Summary card element.
 */
function SummaryCard({ label, value, subtitle }: SummaryCardProps): JSX.Element {
  return (
    <div className="rounded-xl bg-white border border-white p-6 shadow-sm">
      <p className="text-[11px] font-bold tracking-widest uppercase text-outline">{label}</p>
      <p className="mt-2 text-3xl font-black text-on-surface">{value}</p>
      <p className="mt-1 text-xs text-outline">{subtitle}</p>
    </div>
  );
}

/** Props for one failures table row. */
interface FailureRowProps {
  /** Failure record from API. */
  readonly row: {
    readonly id: string;
    readonly stage: string;
    readonly company: string;
    readonly position: string;
    readonly error_code: string;
    readonly attempts: number;
    readonly max_attempts: number;
    readonly time: string;
    readonly status: string;
    readonly error_trace: readonly string[];
    readonly platform: string;
    readonly job_posting_url: string;
  };
  /** Whether expanded detail is visible. */
  readonly expanded: boolean;
  /** Whether retry mutation is currently pending for this row. */
  readonly pendingRetry: boolean;
  /** Row toggle callback. */
  readonly onToggle: () => void;
  /** Retry callback. */
  readonly onRetry: () => void;
}

/**
 * Render one failure row and optional expanded detail panel.
 *
 * @param props - {@link FailureRowProps}
 * @returns Row with optional detail panel.
 */
function FailureRow({
  row,
  expanded,
  pendingRetry,
  onToggle,
  onRetry,
}: FailureRowProps): JSX.Element {
  return (
    <>
      <tr className="border-t border-outline-variant/30 hover:bg-surface-container-low/50 transition-colors">
        <td className="px-6 py-4">
          <span
            className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider ${stageClass(row.stage)}`}
          >
            {row.stage}
          </span>
        </td>
        <td className="px-6 py-4 font-semibold text-on-surface">{row.company}</td>
        <td className="px-6 py-4 text-on-surface-variant">{row.position}</td>
        <td className="px-6 py-4">
          <code className="rounded bg-error-container px-2 py-0.5 text-xs font-semibold text-on-error-container">
            {row.error_code}
          </code>
        </td>
        <td className="px-6 py-4 text-xs text-on-surface-variant">
          {row.attempts}/{row.max_attempts}
        </td>
        <td className="px-6 py-4">
          <span
            className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider ${statusClass(row.status)}`}
          >
            {row.status}
          </span>
        </td>
        <td className="px-6 py-4 text-xs text-on-surface-variant">{row.time}</td>
        <td className="px-6 py-4 text-right">
          <div className="inline-flex items-center gap-2">
            <button
              className="rounded-lg border border-outline-variant px-2 py-1 text-xs font-semibold text-on-surface-variant"
              onClick={onToggle}
            >
              {expanded ? "Hide" : "View"}
            </button>
            <button
              className="rounded-lg px-2 py-1 text-xs font-semibold text-white disabled:opacity-60"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={onRetry}
              disabled={pendingRetry}
            >
              {pendingRetry ? "Retrying..." : "Retry"}
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="bg-surface-container-low/60">
          <td className="px-6 py-6" colSpan={8}>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-widest font-bold text-outline">
                  Job Details
                </p>
                <p className="text-sm font-semibold text-on-surface">{row.company}</p>
                <p className="text-xs text-on-surface-variant">{row.position}</p>
                <p className="text-xs text-on-surface-variant">Platform: {row.platform}</p>
                <a
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                  href={row.job_posting_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  View Job Posting
                  <span className="material-symbols-outlined text-sm">open_in_new</span>
                </a>
              </div>

              <div className="lg:col-span-2 space-y-2">
                <p className="text-[11px] uppercase tracking-widest font-bold text-outline">
                  Error Trace
                </p>
                <div className="rounded-xl bg-[#171922] p-4 text-xs text-slate-100 font-mono whitespace-pre-wrap">
                  {(row.error_trace.length === 0
                    ? ["No error trace available."]
                    : row.error_trace
                  ).join("\n")}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/** Props for pagination footer. */
interface PaginationProps {
  /** Current 1-based page number. */
  readonly currentPage: number;
  /** Total number of pages available. */
  readonly totalPages: number;
  /** Total items in query result. */
  readonly totalItems: number;
  /** Page-change callback. */
  readonly onPageChange: (page: number) => void;
}

/**
 * Render pagination controls for the failures table.
 *
 * @param props - {@link PaginationProps}
 * @returns Pagination footer element.
 */
function Pagination({
  currentPage,
  totalPages,
  totalItems,
  onPageChange,
}: PaginationProps): JSX.Element {
  const safeTotalPages = Math.max(1, totalPages);

  return (
    <div className="px-6 py-4 border-t border-outline-variant/30 flex items-center justify-between">
      <p className="text-xs font-medium text-outline">
        Showing page {currentPage} of {safeTotalPages} ({totalItems} failures)
      </p>
      <div className="flex items-center gap-2">
        <button
          className="rounded-lg border border-outline-variant px-3 py-1.5 text-xs font-semibold text-on-surface-variant disabled:opacity-40"
          onClick={() => {
            onPageChange(Math.max(1, currentPage - 1));
          }}
          disabled={currentPage <= 1}
        >
          Prev
        </button>
        <button
          className="rounded-lg border border-outline-variant px-3 py-1.5 text-xs font-semibold text-on-surface-variant disabled:opacity-40"
          onClick={() => {
            onPageChange(Math.min(safeTotalPages, currentPage + 1));
          }}
          disabled={currentPage >= safeTotalPages}
        >
          Next
        </button>
      </div>
    </div>
  );
}
