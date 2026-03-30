/**
 * @packageDocumentation
 *
 * Human Review queue page wired to backend data and reviewer actions.
 */

import type { ChangeEvent, JSX } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toHumanReviewModel, toHumanReviewRow } from "@/lib/api/adapters";
import {
  completeHumanReview,
  dismissHumanReview,
  fetchHumanReviewQueue,
} from "@/lib/api/client";
import {
  COLOR_ON_SURFACE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";

const PAGE_SIZE = 20;

/**
 * Convert raw timestamp into a short local display string.
 *
 * @param rawValue - Raw API timestamp string.
 * @returns Localized date and time string.
 */
function formatAppliedDate(rawValue: string): string {
  const parsedDate = new Date(rawValue);
  if (Number.isNaN(parsedDate.valueOf())) {
    return rawValue;
  }
  return parsedDate.toLocaleString();
}

/**
 * Resolve row style classes for queue status values.
 *
 * @param status - Handoff status value from API.
 * @returns Tailwind class list for badge rendering.
 */
function statusBadgeClass(status: string): string {
  if (status === "PENDING_REVIEW") {
    return "bg-warning-container text-on-warning-container";
  }
  if (status === "APPROVED") {
    return "bg-emerald-100 text-emerald-700";
  }
  if (status === "REJECTED") {
    return "bg-rose-100 text-rose-700";
  }
  return "bg-surface-container text-on-surface-variant";
}

/**
 * Resolve text label for queue status values.
 *
 * @param status - Handoff status value from API.
 * @returns Human-readable status label.
 */
function statusLabel(status: string): string {
  if (status === "PENDING_REVIEW") {
    return "Needs Review";
  }
  if (status === "APPROVED") {
    return "Approved";
  }
  if (status === "REJECTED") {
    return "Dismissed";
  }
  return status;
}

/**
 * Resolve compact confidence style classes.
 *
 * @param confidence - Confidence tier from API.
 * @returns Tailwind class list.
 */
function confidenceClass(confidence: string): string {
  if (confidence === "high") {
    return "bg-emerald-50 text-emerald-700 border border-emerald-200";
  }
  if (confidence === "medium") {
    return "bg-warning-container text-on-warning-container border border-warning";
  }
  return "bg-rose-50 text-rose-700 border border-rose-200";
}

/**
 * Human Review page root component.
 *
 * @returns Fully wired queue page with actions and pagination.
 */
export function HumanReviewPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("PENDING_REVIEW");
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  const reviewQuery = useQuery({
    queryKey: [
      "human-review",
      {
        search: searchQuery,
        status: statusFilter,
        page: currentPage,
        pageSize: PAGE_SIZE,
      },
    ],
    queryFn: async () =>
      toHumanReviewModel(
        await fetchHumanReviewQueue({
          search: searchQuery,
          status: statusFilter,
          page: currentPage,
          pageSize: PAGE_SIZE,
        }),
      ),
  });

  const completeMutation = useMutation({
    mutationFn: (handoffId: number) => completeHumanReview(handoffId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["human-review"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", "stats"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["costs"] });
      setExpandedRowId(null);
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (handoffId: number) => dismissHumanReview(handoffId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["human-review"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", "stats"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["costs"] });
      setExpandedRowId(null);
    },
  });

  const rows = useMemo(
    () => (reviewQuery.data?.items ?? []).map((row) => toHumanReviewRow(row)),
    [reviewQuery.data?.items],
  );

  const pendingCount = rows.filter((row) => row.status === "PENDING_REVIEW").length;
  const reviewedCount = rows.length - pendingCount;
  const totalPages = reviewQuery.data?.total_pages ?? 1;

  function handleSearchChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
    setCurrentPage(1);
  }

  function handleStatusChange(event: ChangeEvent<HTMLSelectElement>): void {
    setStatusFilter(event.target.value);
    setCurrentPage(1);
  }

  function handleReviewNext(): void {
    const nextPending = rows.find((row) => row.status === "PENDING_REVIEW");
    if (nextPending !== undefined) {
      setExpandedRowId(nextPending.id);
    }
  }

  const hasMutationError = completeMutation.isError || dismissMutation.isError;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-3xl font-black tracking-tight" style={{ color: COLOR_ON_SURFACE }}>
            Human Review Queue
          </h2>
          <p className="text-sm text-on-surface-variant mt-1">
            Verify unresolved fields and complete or dismiss applications.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            className="rounded-full border border-outline-variant px-5 py-2.5 text-sm font-semibold text-on-surface-variant"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}99` }}
            disabled
            title="CSV export is deferred for this pass."
          >
            Export CSV
          </button>
          <button
            type="button"
            className="rounded-full px-6 py-2.5 text-sm font-bold text-white"
            style={{ backgroundColor: COLOR_PRIMARY }}
            onClick={handleReviewNext}
          >
            Review Next
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <SummaryCard label="Queue Size" value={String(reviewQuery.data?.total_items ?? 0)} subtitle="Filtered result" />
        <SummaryCard label="Needs Review" value={String(pendingCount)} subtitle="On this page" />
        <SummaryCard label="Resolved" value={String(reviewedCount)} subtitle="On this page" />
      </div>

      <div className="bg-white rounded-xl border border-white p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="relative md:w-[420px]">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline">
            search
          </span>
          <input
            className="w-full rounded-lg border border-outline-variant bg-surface-container-low py-2 pl-10 pr-3 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            placeholder="Search company or position..."
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </div>

        <select
          className="rounded-lg border bg-white px-3 py-2 text-sm"
          style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
          value={statusFilter}
          onChange={handleStatusChange}
        >
          <option value="">All Statuses</option>
          <option value="PENDING_REVIEW">PENDING_REVIEW</option>
          <option value="APPROVED">APPROVED</option>
          <option value="REJECTED">REJECTED</option>
        </select>
      </div>

      {(reviewQuery.isError || hasMutationError) && (
        <div className="rounded-xl border border-error-container bg-error-container px-4 py-3 text-sm text-on-error-container">
          Failed to load or update review queue data. Use Sync now to retry.
        </div>
      )}

      <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-white">
        <table className="w-full text-left border-collapse">
          <thead style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}>
            <tr>
              {["COMPANY", "POSITION", "STATUS", "CONFIDENCE", "APPLIED", ""].map((column) => (
                <th
                  key={column}
                  className={`px-6 py-4 text-[10px] font-bold tracking-widest uppercase ${column === "" ? "text-right" : ""}`}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ReviewRow
                key={row.id}
                row={row}
                expanded={expandedRowId === row.id}
                pendingComplete={completeMutation.isPending && completeMutation.variables === row.id}
                pendingDismiss={dismissMutation.isPending && dismissMutation.variables === row.id}
                onToggle={() => {
                  setExpandedRowId((previous) => (previous === row.id ? null : row.id));
                }}
                onComplete={() => {
                  completeMutation.mutate(row.id);
                }}
                onDismiss={() => {
                  dismissMutation.mutate(row.id);
                }}
              />
            ))}

            {reviewQuery.isLoading && (
              <tr>
                <td className="px-6 py-10 text-sm text-outline" colSpan={6}>
                  Loading review queue...
                </td>
              </tr>
            )}

            {!reviewQuery.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-6 py-10 text-sm text-outline" colSpan={6}>
                  No review records match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={reviewQuery.data?.total_items ?? 0}
          onPageChange={(page) => {
            setCurrentPage(page);
            setExpandedRowId(null);
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
 * Render one summary card.
 *
 * @param props - Card display content.
 * @returns Summary card UI element.
 */
function SummaryCard({ label, value, subtitle }: SummaryCardProps): JSX.Element {
  return (
    <div className="rounded-xl bg-white border border-white p-6 shadow-sm">
      <p className="text-[11px] font-bold tracking-widest uppercase text-outline">{label}</p>
      <p className="mt-2 text-3xl font-black text-on-surface">
        {value}
      </p>
      <p className="mt-1 text-xs text-outline">{subtitle}</p>
    </div>
  );
}

/** Props for one review table row. */
interface ReviewRowProps {
  /** Row payload from backend. */
  readonly row: {
    readonly id: number;
    readonly company_name: string;
    readonly position: string;
    readonly status: string;
    readonly confidence_pct: number;
    readonly applied_date: string;
    readonly agent_diagnostic: string;
    readonly job_posting_url: string;
    readonly resume_file_name: string;
    readonly unresolved_fields: readonly {
      readonly field_name: string;
      readonly ai_answer: string;
      readonly reasoning: string;
      readonly answer_confidence: string;
    }[];
  };
  /** Whether details panel is expanded. */
  readonly expanded: boolean;
  /** Whether complete mutation is in-flight for this row. */
  readonly pendingComplete: boolean;
  /** Whether dismiss mutation is in-flight for this row. */
  readonly pendingDismiss: boolean;
  /** Toggle expanded panel callback. */
  readonly onToggle: () => void;
  /** Mark-complete callback. */
  readonly onComplete: () => void;
  /** Dismiss callback. */
  readonly onDismiss: () => void;
}

/**
 * Render one review row and optional expanded details panel.
 *
 * @param props - Review row render props.
 * @returns Row and optional expanded panel.
 */
function ReviewRow({
  row,
  expanded,
  pendingComplete,
  pendingDismiss,
  onToggle,
  onComplete,
  onDismiss,
}: ReviewRowProps): JSX.Element {
  const unresolvedCount = row.unresolved_fields.length;
  const isPending = row.status === "PENDING_REVIEW";

  return (
    <>
      <tr className="border-t border-outline-variant/30 hover:bg-surface-container-low/50 transition-colors">
        <td className="px-6 py-4 font-semibold text-on-surface">{row.company_name}</td>
        <td className="px-6 py-4 text-on-surface-variant">{row.position}</td>
        <td className="px-6 py-4">
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider ${statusBadgeClass(row.status)}`}>
            {statusLabel(row.status)}
          </span>
        </td>
        <td className="px-6 py-4 text-xs font-semibold text-on-surface-variant">{row.confidence_pct}%</td>
        <td className="px-6 py-4 text-xs text-on-surface-variant">{formatAppliedDate(row.applied_date)}</td>
        <td className="px-6 py-4 text-right">
          <button className="rounded-lg border border-outline-variant px-2 py-1 text-xs font-semibold text-on-surface-variant" onClick={onToggle}>
            {expanded ? "Hide" : isPending ? "Review" : "View"}
          </button>
        </td>
      </tr>

      {expanded && (
        <tr className="bg-surface-container-low/60">
          <td className="px-6 py-6" colSpan={6}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-3">
                <p className="text-[11px] uppercase tracking-widest font-bold text-outline">Why Flagged</p>
                <div className="rounded-xl border border-outline-variant bg-white p-4 text-sm text-on-surface-variant leading-6">
                  {row.agent_diagnostic}
                </div>
                <div className="flex flex-col gap-2 text-xs">
                  <a
                    className="inline-flex items-center gap-1 font-semibold text-primary hover:underline"
                    href={row.job_posting_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View Job Posting
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                  </a>
                  <p className="text-on-surface-variant">Resume: {row.resume_file_name}</p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] uppercase tracking-widest font-bold text-outline">
                    AI Recommended Answers
                  </p>
                  <span className="text-xs font-semibold text-outline">
                    {unresolvedCount} unresolved field{unresolvedCount === 1 ? "" : "s"}
                  </span>
                </div>

                {unresolvedCount === 0 ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
                    No unresolved fields remain for this handoff.
                  </div>
                ) : (
                  <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
                    {row.unresolved_fields.map((field) => (
                      <div key={field.field_name} className="rounded-xl border border-outline-variant bg-white p-4 space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-xs font-bold uppercase tracking-wider text-outline">
                            {field.field_name}
                          </p>
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-semibold ${confidenceClass(field.answer_confidence)}`}
                          >
                            {field.answer_confidence}
                          </span>
                        </div>
                        <p className="text-sm font-semibold text-on-surface">{field.ai_answer}</p>
                        <p className="text-xs italic text-on-surface-variant">{field.reasoning}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="mt-6 border-t border-outline-variant pt-4 flex justify-end gap-3">
              <button
                type="button"
                className="rounded-full border border-outline-variant px-5 py-2 text-sm font-semibold text-on-surface-variant disabled:opacity-50"
                style={{ borderColor: `${COLOR_OUTLINE_VARIANT}99` }}
                onClick={onDismiss}
                disabled={!isPending || pendingDismiss || pendingComplete}
              >
                {pendingDismiss ? "Dismissing..." : "Dismiss"}
              </button>
              <button
                type="button"
                className="rounded-full px-5 py-2 text-sm font-bold text-white disabled:opacity-50"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onComplete}
                disabled={!isPending || pendingComplete || pendingDismiss}
              >
                {pendingComplete ? "Completing..." : "Mark Complete"}
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/** Props for pagination controls. */
interface PaginationProps {
  /** Active 1-based page number. */
  readonly currentPage: number;
  /** Total pages available. */
  readonly totalPages: number;
  /** Total items in filtered query. */
  readonly totalItems: number;
  /** Callback for page changes. */
  readonly onPageChange: (page: number) => void;
}

/**
 * Render table pagination footer.
 *
 * @param props - Pagination display and callbacks.
 * @returns Pagination footer element.
 */
function Pagination({ currentPage, totalPages, totalItems, onPageChange }: PaginationProps): JSX.Element {
  const safeTotalPages = Math.max(1, totalPages);

  return (
    <div className="px-6 py-4 border-t border-outline-variant/30 flex items-center justify-between">
      <p className="text-xs font-medium text-outline">
        Showing page {currentPage} of {safeTotalPages} ({totalItems} records)
      </p>
      <div className="flex items-center gap-2">
        <button
          className="rounded-lg border border-outline-variant px-3 py-1.5 text-xs font-semibold text-on-surface-variant disabled:opacity-40"
          onClick={() => {
            onPageChange(Math.max(1, currentPage - 1));
          }}
          disabled={currentPage <= 1}
        >
          Previous
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
