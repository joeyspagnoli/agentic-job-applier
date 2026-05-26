/**
 * @packageDocumentation
 *
 * Jobs dashboard page with filter tabs, keyboard navigation, expandable
 * rows, and manual import integration.
 */

import type { ChangeEvent, JSX } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toJobsRows, type JobsRowModel } from "@/lib/api/adapters";
import {
  ApplyRunConflictError,
  deleteTailorRun,
  enqueueTailorRun,
  fetchAutomationSettings,
  fetchJobs,
  fetchJobsNow,
  getTailoredResumeUrl,
  postApplyRun,
  relaunchApplyByJobHash,
  retryTailorRun,
} from "@/lib/api/client";
import type { ApplyRunDto } from "@/lib/api/types";
import { ApplyButton } from "@/pages/jobs/ApplyButton";
import { NotTailoredModal } from "@/pages/jobs/NotTailoredModal";
import { TailorPlanPanel } from "@/pages/jobs/TailorPlanPanel";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";
import { toSafeJobPostingUrl } from "@/pages/jobs-url";
import { ImportJobModal } from "@/components/ImportJobModal";

const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

/** Filter tab definition for the status filter bar. */
interface FilterTab {
  /** Filter value sent to backend (empty = all). */
  readonly value: string;
  /** Display label for the tab. */
  readonly label: string;
}

/** Ordered list of filter tabs shown above the table. */
const FILTER_TABS: readonly FilterTab[] = [
  { value: "", label: "All" },
  { value: "new", label: "New" },
  { value: "QUALIFIED", label: "Qualified" },
  { value: "APPLIED", label: "Applied" },
  { value: "FILTERED", label: "Filtered" },
  { value: "REJECTED", label: "Rejected" },
];

/**
 * Source options for the source filter dropdown.
 *
 * Must mirror the canonical labels returned by `_source_label` in
 * `api/services/sources.py`. Adding a new fetcher family means updating
 * both the backend mapping and this list, and adding a regression test
 * in `tests/test_api_jobs_source_filter.py`.
 */
const SOURCE_OPTIONS: readonly string[] = [
  "WORKDAY",
  "GREENHOUSE",
  "JOBSPY",
  "LINKEDIN",
  "ICIMS",
  "TALEO",
  "LEVER",
  "ASHBY",
  "ADZUNA",
  "GITHUB_REPOS",
  "MANUAL_IMPORT",
];

/**
 * Convert raw discovery timestamp into short display text.
 *
 * @param rawValue - ISO timestamp string from backend.
 * @returns Short localized date/time string.
 */
function formatDiscovered(rawValue: string): string {
  const parsedDate = new Date(rawValue);
  if (Number.isNaN(parsedDate.valueOf())) {
    return rawValue;
  }
  return parsedDate.toLocaleString();
}

/**
 * Resolve row badge classes for job source labels.
 *
 * @param source - Source label from API.
 * @returns Tailwind class string.
 */
function sourceBadgeClass(source: string): string {
  const lower = source.toLowerCase();
  if (lower === "greenhouse") {
    return "bg-primary-fixed text-primary";
  }
  if (lower === "workday") {
    return "bg-emerald-100 text-emerald-700";
  }
  if (lower === "lever" || lower === "ashby") {
    return "bg-violet-100 text-violet-700";
  }
  return "bg-surface-container text-on-surface-variant";
}

/**
 * Resolve row badge classes for job status labels.
 *
 * @param status - Job status from API.
 * @returns Tailwind class string.
 */
function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "APPLIED") {
    return "bg-success-container text-on-success-container";
  }
  if (normalized.includes("PENDING") || normalized === "NEW") {
    return "bg-warning-container text-on-warning-container";
  }
  if (normalized.includes("FAILED")) {
    return "bg-error-container text-on-error-container";
  }
  if (normalized === "FILTERED" || normalized === "REJECTED") {
    return "bg-surface-container text-on-surface-variant";
  }
  return "bg-primary-fixed text-primary";
}

/** Props for the JobsPage component. */
interface JobsPageProps {
  /**
   * When `true`, only list jobs with a non-deleted tailor_run. Used by
   * the Tailored Resumes sidebar page to reuse this component.
   */
  readonly hasTailorRunFilter?: boolean;
}

/**
 * Jobs dashboard page component.
 *
 * @param props - {@link JobsPageProps}
 * @returns The full page content rendered inside AppLayout.
 */
export function JobsPage({ hasTailorRunFilter = false }: JobsPageProps = {}): JSX.Element {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [focusedRowIndex, setFocusedRowIndex] = useState<number>(-1);
  const [isImportOpen, setIsImportOpen] = useState<boolean>(false);

  const [justTriggered, setJustTriggered] = useState<boolean>(false);

  const queryClient = useQueryClient();
  const tableRef = useRef<HTMLTableSectionElement | null>(null);

  const fetchJobsMutation = useMutation({
    mutationFn: fetchJobsNow,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setJustTriggered(true);
      window.setTimeout(() => {
        setJustTriggered(false);
      }, 2500);
    },
  });

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [searchQuery]);

  const jobsQuery = useQuery({
    queryKey: [
      "jobs",
      {
        search: debouncedSearchQuery,
        status: statusFilter,
        source: sourceFilter,
        page: currentPage,
        pageSize: PAGE_SIZE,
        hasTailorRun: hasTailorRunFilter,
      },
    ],
    queryFn: () =>
      fetchJobs({
        search: debouncedSearchQuery,
        status: statusFilter,
        source: sourceFilter,
        page: currentPage,
        pageSize: PAGE_SIZE,
        hasTailorRun: hasTailorRunFilter,
      }),
    // Auto-refetch every 5s while any visible row has an in-flight tailor run
    // (PENDING or RUNNING). Without this the row sits on "Tailoring…" until
    // the user navigates away and back.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data === undefined) {
        return false;
      }
      const hasActive = data.items.some((item) => {
        const status = item.tailor_run?.status;
        return status === "PENDING" || status === "RUNNING";
      });
      return hasActive ? 5000 : false;
    },
  });

  const rows = useMemo(() => (jobsQuery.data ? toJobsRows(jobsQuery.data) : []), [jobsQuery.data]);
  const totalItems = jobsQuery.data?.total_items ?? 0;
  const totalPages = jobsQuery.data?.total_pages ?? 1;

  /**
   * Handle keyboard navigation within the job list.
   *
   * @param event - Keyboard event from the table container.
   */
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent): void => {
      if (rows.length === 0) {
        return;
      }

      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        setFocusedRowIndex((prev) => Math.min(prev + 1, rows.length - 1));
      } else if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        setFocusedRowIndex((prev) => Math.max(prev - 1, 0));
      } else if (event.key === "Enter" && focusedRowIndex >= 0) {
        event.preventDefault();
        const row = rows[focusedRowIndex];
        setExpandedRowId((prev) => (prev === row.id ? null : row.id));
      } else if (event.key === "Escape") {
        setExpandedRowId(null);
        setFocusedRowIndex(-1);
      }
    },
    [rows, focusedRowIndex],
  );

  /**
   * Handle search input changes.
   *
   * @param event - Input change event.
   */
  function handleSearchChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
    setCurrentPage(1);
    setFocusedRowIndex(-1);
  }

  /**
   * Handle source filter dropdown change.
   *
   * @param event - Select change event.
   */
  function handleSourceChange(event: ChangeEvent<HTMLSelectElement>): void {
    setSourceFilter(event.target.value);
    setCurrentPage(1);
    setFocusedRowIndex(-1);
  }

  return (
    <div className="p-8 max-w-[1400px] mx-auto space-y-6">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-fluid-xs font-medium" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            {totalItems.toLocaleString()} jobs discovered
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="px-4 py-2 rounded-xl border text-sm font-semibold transition-all"
            style={{ borderColor: COLOR_OUTLINE_VARIANT, color: COLOR_ON_SURFACE_VARIANT }}
            onClick={() => {
              setIsImportOpen(true);
            }}
          >
            <span className="material-symbols-outlined text-[16px] align-text-bottom mr-1">
              add
            </span>
            Import Job
          </button>
          <button
            disabled={fetchJobsMutation.isPending}
            className="px-4 py-2 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click disabled:opacity-60"
            style={{ backgroundColor: COLOR_PRIMARY }}
            onClick={() => {
              fetchJobsMutation.mutate();
            }}
          >
            {fetchJobsMutation.isPending ? (
              <>
                Fetching
                <span className="inline-flex gap-px ml-0.5" aria-hidden="true">
                  <span className="animate-bounce [animation-delay:-0.3s]">.</span>
                  <span className="animate-bounce [animation-delay:-0.15s]">.</span>
                  <span className="animate-bounce">.</span>
                </span>
              </>
            ) : justTriggered ? (
              "Triggered!"
            ) : (
              "Fetch Jobs Now"
            )}
          </button>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-1">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.value}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              style={{
                backgroundColor: statusFilter === tab.value ? COLOR_PRIMARY : "transparent",
                color: statusFilter === tab.value ? "#ffffff" : COLOR_ON_SURFACE_VARIANT,
              }}
              onClick={() => {
                setStatusFilter(tab.value);
                setCurrentPage(1);
                setFocusedRowIndex(-1);
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Search + source filter */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px]"
              style={{ color: COLOR_OUTLINE }}
            >
              search
            </span>
            <input
              className="w-[280px] rounded-xl border py-2 pl-9 pr-3 text-sm transition-colors"
              style={{
                borderColor: `${COLOR_OUTLINE_VARIANT}66`,
                backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
              }}
              placeholder="Search company or role..."
              value={searchQuery}
              onChange={handleSearchChange}
            />
          </div>
          <select
            className="rounded-xl border px-3 py-2 text-sm"
            style={{
              borderColor: `${COLOR_OUTLINE_VARIANT}66`,
              backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
            }}
            value={sourceFilter}
            onChange={handleSourceChange}
          >
            <option value="">All Sources</option>
            {SOURCE_OPTIONS.map((src) => (
              <option key={src} value={src}>
                {src}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Error state */}
      {jobsQuery.isError && (
        <div className="rounded-xl border border-error-container bg-error-container px-4 py-3 text-sm text-on-error-container">
          Failed to load jobs table data. Use Sync now to retry.
        </div>
      )}

      {/* Keyboard hint */}
      <div className="flex items-center gap-4 text-[11px]" style={{ color: COLOR_OUTLINE }}>
        <span>
          <kbd className="px-1 py-0.5 rounded bg-surface-container font-mono text-[10px]">↑↓</kbd>{" "}
          navigate
        </span>
        <span>
          <kbd className="px-1 py-0.5 rounded bg-surface-container font-mono text-[10px]">
            Enter
          </kbd>{" "}
          expand
        </span>
        <span>
          <kbd className="px-1 py-0.5 rounded bg-surface-container font-mono text-[10px]">Esc</kbd>{" "}
          close
        </span>
      </div>

      {/* Jobs table */}
      <div
        className="rounded-xl overflow-hidden ambient-shadow border"
        style={{ borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        role="grid"
        aria-label="Jobs list"
      >
        <table className="w-full text-left border-collapse">
          <thead style={{ backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}>
            <tr>
              {["COMPANY", "POSITION", "LOCATION", "SOURCE", "STATUS", "DISCOVERED", ""].map(
                (heading) => (
                  <th
                    key={heading}
                    className="px-5 py-3.5 text-[10px] font-bold tracking-widest uppercase"
                    style={{
                      color: COLOR_ON_SURFACE_VARIANT,
                      textAlign: heading === "" ? "right" : "left",
                    }}
                  >
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody ref={tableRef}>
            {rows.map((row, index) => (
              <JobRow
                key={row.id}
                row={row}
                expanded={expandedRowId === row.id}
                focused={focusedRowIndex === index}
                onToggle={() => {
                  setExpandedRowId((previous) => (previous === row.id ? null : row.id));
                }}
              />
            ))}
            {jobsQuery.isLoading && (
              <tr>
                <td className="px-5 py-10 text-sm" style={{ color: COLOR_OUTLINE }} colSpan={7}>
                  Loading jobs...
                </td>
              </tr>
            )}
            {!jobsQuery.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-5 py-10 text-sm" style={{ color: COLOR_OUTLINE }} colSpan={7}>
                  No jobs match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={totalItems}
          onPageChange={(page) => {
            setCurrentPage(page);
            setExpandedRowId(null);
            setFocusedRowIndex(-1);
          }}
        />
      </div>

      {/* Import modal */}
      <ImportJobModal
        open={isImportOpen}
        onClose={() => {
          setIsImportOpen(false);
        }}
        onImported={() => {
          void queryClient.invalidateQueries({ queryKey: ["jobs"] });
        }}
      />
    </div>
  );
}

/** Copy shown when the tailor model returned an empty edits list. */
const TAILOR_BAILED_COPY = "The tailor model declined to propose edits.";
/** Copy shown when every proposed edit referenced an unknown listing/bullet ID. */
const ALL_EDITS_DROPPED_COPY =
  "The tailor's edits referenced unknown IDs and were dropped.";
/** Copy shown when the reviewer genuinely chose the base resume over the tailor. */
const REVIEWER_CHOSE_BASE_COPY =
  "Reviewer thought the base resume was fine for this role.";

/**
 * Map a SUCCESS-state tailor run's verdict + reason to user-visible copy.
 *
 * @param verdict - Uppercase tailor-run verdict (`NO_IMPROVEMENT`,
 *   `PAGE_FIT_FAILED`, or any other base-served outcome).
 * @param reviewReason - Structured `reason` pulled from
 *   `review_runs.review_report_json`, or `null` when absent.
 * @returns Display string for the tailored-resume cell.
 */
function resolveVerdictCopy(
  verdict: string,
  reviewReason: string | null,
): string {
  if (verdict === "PAGE_FIT_FAILED") {
    return "Couldn't fit on one page — served base.";
  }
  if (verdict === "NO_IMPROVEMENT") {
    if (reviewReason === "tailor_bailed") {
      return TAILOR_BAILED_COPY;
    }
    if (reviewReason === "all_edits_dropped") {
      return ALL_EDITS_DROPPED_COPY;
    }
    return REVIEWER_CHOSE_BASE_COPY;
  }
  return "Served base resume.";
}

/** Props for the tailored-resume cell inside an expanded job row. */
interface TailoredResumeCellProps {
  /** Row data including the embedded tailor_run snapshot. */
  readonly row: JobsRowModel;
}

/**
 * Render the tailored-resume control inside an expanded job row.
 *
 * The control surfaces six states driven by `row.tailorRun`:
 * idle / PENDING / RUNNING / SUCCESS (with verdict variants) / FAILED.
 * Each state shows the correct action button — "Tailor resume",
 * "Download PDF", "Delete & retry" — and writes back through the
 * tailor-run API.
 *
 * @param props - {@link TailoredResumeCellProps}
 * @returns A short status block plus the active action button.
 */
function TailoredResumeCell({ row }: TailoredResumeCellProps): JSX.Element {
  const queryClient = useQueryClient();
  const { data: automation } = useQuery({
    queryKey: ["automation-settings"],
    queryFn: fetchAutomationSettings,
  });
  const isAutonomous = automation?.tailor_mode === "autonomous";

  const enqueueMutation = useMutation({
    mutationFn: (opts?: { applyAfter?: boolean }) =>
      enqueueTailorRun(row.jobHash, opts),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: unknown) => {
      // RUN_ALREADY_EXISTS races with the jobs refetch — the row is
      // already authoritative, so silently re-fetch instead of showing
      // a red error banner under the "Tailor resume" button.
      if (
        error !== null &&
        typeof error === "object" &&
        "code" in error &&
        (error as { code: unknown }).code === "RUN_ALREADY_EXISTS"
      ) {
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
        return;
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (runId: number) => deleteTailorRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (runId: number) => retryTailorRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  // Apply-run local state — the jobs list does not yet embed apply_run
  // snapshots, so we hold the latest known run here after user-initiated actions.
  const [applyRun, setApplyRun] = useState<ApplyRunDto | null>(null);
  const [isNotTailoredModalOpen, setIsNotTailoredModalOpen] = useState(false);
  const [applyErrorMessage, setApplyErrorMessage] = useState<string | null>(null);

  const applyMutation = useMutation({
    mutationFn: (opts?: { resumeMode?: "tailored" | "base" }) =>
      postApplyRun(row.jobHash, opts),
    onSuccess: (data) => {
      // Seed local apply state so the button transitions immediately.
      setApplyRun({
        id: data.apply_run_id,
        job_hash: data.job_hash,
        status: data.status as ApplyRunDto["status"],
        outcome: null,
        ats_platform: null,
        completed_at: null,
        screenshot_path: null,
        error: null,
      });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: unknown) => {
      if (error instanceof ApplyRunConflictError) {
        // Non-blocking notice — an active run already exists.
        setApplyErrorMessage("An apply run is already in progress for this job.");
        return;
      }
      setApplyErrorMessage(error instanceof Error ? error.message : "Apply failed. Please try again.");
    },
  });

  const relaunchMutation = useMutation({
    mutationFn: () => relaunchApplyByJobHash(row.jobHash),
    onSuccess: (data) => {
      // Drop the local apply run snapshot back to PENDING so the
      // ApplyButton transitions away from the "needs review" badge
      // and the polling loop catches the rest of the lifecycle.
      setApplyRun({
        id: data.apply_run_id,
        job_hash: data.job_hash,
        status: data.status as ApplyRunDto["status"],
        outcome: null,
        ats_platform: null,
        completed_at: null,
        screenshot_path: null,
        error: null,
      });
      setApplyErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["human-review"] });
    },
    onError: (error: unknown) => {
      setApplyErrorMessage(
        error instanceof Error ? error.message : "Relaunch failed.",
      );
    },
  });

  const handleRelaunch = useCallback(() => {
    setApplyErrorMessage(null);
    relaunchMutation.mutate();
  }, [relaunchMutation]);

  const handleApplyTailored = useCallback(() => {
    // Apply button on a SUCCESS tailor — backend uses the existing
    // review run, no body needed.
    setIsNotTailoredModalOpen(false);
    setApplyErrorMessage(null);
    applyMutation.mutate(undefined);
  }, [applyMutation]);

  const handleApplyBase = useCallback(() => {
    // "No, skip tailoring" from the NotTailoredModal — backend
    // synthesizes a tailor+review chain and ships the base PDF.
    setIsNotTailoredModalOpen(false);
    setApplyErrorMessage(null);
    applyMutation.mutate({ resumeMode: "base" });
  }, [applyMutation]);

  const handleRequestTailorChoice = useCallback(() => {
    // Open the NotTailoredModal so the user picks between "tailor then
    // apply" and "skip tailoring". Routing the button directly to the
    // tailor enqueue is what caused the 409 Bug #1 regression.
    setApplyErrorMessage(null);
    setIsNotTailoredModalOpen(true);
  }, []);

  const handleTailorThenApply = useCallback(() => {
    // "Yes, tailor my resume" from the NotTailoredModal — the backend
    // persists the auto-apply intent on the tailor row and enqueues
    // the apply automatically when the pipeline finishes. No
    // client-side mutation chaining.
    setIsNotTailoredModalOpen(false);
    setApplyErrorMessage(null);
    enqueueMutation.mutate({ applyAfter: true });
  }, [enqueueMutation]);

  const tailorRun = row.tailorRun;
  const baseDownloadUrl = getTailoredResumeUrl(row.jobHash);
  // RUN_ALREADY_EXISTS is racy with the jobs refetch — the row state
  // catches up and hides the button anyway, so don't render a red
  // banner under a button whose underlying action already succeeded.
  const rawEnqueueError = enqueueMutation.error;
  const errorMessage =
    rawEnqueueError !== null &&
    !(
      typeof rawEnqueueError === "object" &&
      "code" in rawEnqueueError &&
      (rawEnqueueError as { code: unknown }).code === "RUN_ALREADY_EXISTS"
    )
      ? (rawEnqueueError as Error).message
      : null;
  const deleteErrorMessage = deleteMutation.error
    ? (deleteMutation.error as Error).message
    : null;
  const retryErrorMessage = retryMutation.error
    ? (retryMutation.error as Error).message
    : null;

  if (tailorRun === null) {
    return (
      <>
        <div className="text-xs space-y-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <p>Tailored Resume: Not generated yet</p>
          {isAutonomous ? (
            <p style={{ color: COLOR_OUTLINE }}>
              Automation mode is autonomous — runs trigger from the worker.
            </p>
          ) : (
            <button
              type="button"
              className="px-4 py-2 rounded-xl text-xs font-bold text-white transition-all scale-98-on-click disabled:opacity-60"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={(e) => {
                e.stopPropagation();
                enqueueMutation.mutate(undefined);
              }}
              disabled={enqueueMutation.isPending}
            >
              {enqueueMutation.isPending ? "Enqueuing…" : "Tailor resume"}
            </button>
          )}
          {errorMessage !== null ? (
            <p style={{ color: "#b91c1c" }}>{errorMessage}</p>
          ) : null}
        </div>
        <div className="mt-2">
          <ApplyButton
            jobHash={row.jobHash}
            tailorRun={null}
            applyRun={applyRun}
            onApply={handleApplyTailored}
            onRequestTailorChoice={handleRequestTailorChoice}
            onRelaunch={handleRelaunch}
            pendingRelaunch={relaunchMutation.isPending}
          />
          {applyErrorMessage !== null ? (
            <p className="text-xs mt-1" style={{ color: "#b91c1c" }}>{applyErrorMessage}</p>
          ) : null}
        </div>
        <NotTailoredModal
          open={isNotTailoredModalOpen}
          onClose={() => setIsNotTailoredModalOpen(false)}
          onApply={handleApplyBase}
          onTailorThenApply={handleTailorThenApply}
        />
      </>
    );
  }

  if (tailorRun.status === "PENDING" || tailorRun.status === "RUNNING") {
    return (
      <>
        <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Tailored Resume: {tailorRun.status === "PENDING" ? "Queued…" : "Tailoring…"}
        </p>
        <div className="mt-2">
          <ApplyButton
            jobHash={row.jobHash}
            tailorRun={tailorRun}
            applyRun={applyRun}
            onApply={handleApplyTailored}
            onRequestTailorChoice={handleRequestTailorChoice}
            onRelaunch={handleRelaunch}
            pendingRelaunch={relaunchMutation.isPending}
          />
        </div>
        <NotTailoredModal
          open={isNotTailoredModalOpen}
          onClose={() => setIsNotTailoredModalOpen(false)}
          onApply={handleApplyBase}
          onTailorThenApply={handleTailorThenApply}
        />
      </>
    );
  }

  if (tailorRun.status === "FAILED") {
    return (
      <>
        <div className="text-xs space-y-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <p>Tailored Resume: Tailor failed — {tailorRun.error ?? "unknown error"}</p>
          <a
            className="font-semibold hover:underline"
            href={baseDownloadUrl}
            target="_blank"
            rel="noreferrer"
            style={{ color: COLOR_PRIMARY }}
          >
            Download base PDF
          </a>
          <button
            type="button"
            className="ml-3 rounded-lg px-3 py-1 text-xs font-semibold border"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}80`, color: COLOR_PRIMARY }}
            onClick={(e) => {
              e.stopPropagation();
              retryMutation.mutate(tailorRun.id);
            }}
            disabled={retryMutation.isPending}
          >
            Delete &amp; retry
          </button>
          {retryErrorMessage !== null ? (
            <p style={{ color: "#b91c1c" }}>{retryErrorMessage}</p>
          ) : null}
        </div>
        <div className="mt-2">
          <ApplyButton
            jobHash={row.jobHash}
            tailorRun={tailorRun}
            applyRun={applyRun}
            onApply={handleApplyTailored}
            onRequestTailorChoice={handleRequestTailorChoice}
            onRelaunch={handleRelaunch}
            pendingRelaunch={relaunchMutation.isPending}
          />
          {applyErrorMessage !== null ? (
            <p className="text-xs mt-1" style={{ color: "#b91c1c" }}>{applyErrorMessage}</p>
          ) : null}
        </div>
        <NotTailoredModal
          open={isNotTailoredModalOpen}
          onClose={() => setIsNotTailoredModalOpen(false)}
          onApply={handleApplyBase}
          onTailorThenApply={handleTailorThenApply}
        />
      </>
    );
  }

  // SUCCESS — verdict drives the copy + button labels.
  const verdict = (tailorRun.verdict ?? "").toUpperCase();
  if (verdict === "TAILORED") {
    return (
      <>
        <div className="text-xs space-y-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <p>Tailored Resume: Reviewer picked the tailored variant.</p>
          <a
            className="font-semibold hover:underline"
            href={baseDownloadUrl}
            target="_blank"
            rel="noreferrer"
            style={{ color: COLOR_PRIMARY }}
          >
            Download PDF
          </a>
          <button
            type="button"
            className="ml-3 rounded-lg px-3 py-1 text-xs font-semibold border"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}80`, color: COLOR_PRIMARY }}
            onClick={(e) => {
              e.stopPropagation();
              deleteMutation.mutate(tailorRun.id);
            }}
            disabled={deleteMutation.isPending}
          >
            Delete tailored
          </button>
          {deleteErrorMessage !== null ? (
            <p style={{ color: "#b91c1c" }}>{deleteErrorMessage}</p>
          ) : null}
        </div>
        {tailorRun.planUrl !== null && <TailorPlanPanel runId={tailorRun.id} />}
        <div className="mt-2">
          <ApplyButton
            jobHash={row.jobHash}
            tailorRun={tailorRun}
            applyRun={applyRun}
            onApply={handleApplyTailored}
            onRequestTailorChoice={handleRequestTailorChoice}
            onRelaunch={handleRelaunch}
            pendingRelaunch={relaunchMutation.isPending}
          />
          {applyErrorMessage !== null ? (
            <p className="text-xs mt-1" style={{ color: "#b91c1c" }}>{applyErrorMessage}</p>
          ) : null}
        </div>
        <NotTailoredModal
          open={isNotTailoredModalOpen}
          onClose={() => setIsNotTailoredModalOpen(false)}
          onApply={handleApplyBase}
          onTailorThenApply={handleTailorThenApply}
        />
      </>
    );
  }

  const verdictCopy = resolveVerdictCopy(verdict, tailorRun.reviewReason);

  return (
    <>
      <div className="text-xs space-y-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        <p>Tailored Resume: {verdictCopy}</p>
        <a
          className="font-semibold hover:underline"
          href={baseDownloadUrl}
          target="_blank"
          rel="noreferrer"
          style={{ color: COLOR_PRIMARY }}
        >
          Download base PDF
        </a>
        <button
          type="button"
          className="ml-3 rounded-lg px-3 py-1 text-xs font-semibold border"
          style={{ borderColor: `${COLOR_OUTLINE_VARIANT}80`, color: COLOR_PRIMARY }}
          onClick={(e) => {
            e.stopPropagation();
            retryMutation.mutate(tailorRun.id);
          }}
          disabled={retryMutation.isPending}
        >
          Delete &amp; retry
        </button>
        {retryErrorMessage !== null ? (
          <p style={{ color: "#b91c1c" }}>{retryErrorMessage}</p>
        ) : null}
      </div>
      <div className="mt-2">
        <ApplyButton
          jobHash={row.jobHash}
          tailorRun={tailorRun}
          applyRun={applyRun}
          onApply={handleApplyTailored}
          onRequestTailorChoice={handleRequestTailorChoice}
            onRelaunch={handleRelaunch}
            pendingRelaunch={relaunchMutation.isPending}
        />
        {applyErrorMessage !== null ? (
          <p className="text-xs mt-1" style={{ color: "#b91c1c" }}>{applyErrorMessage}</p>
        ) : null}
      </div>
      <NotTailoredModal
        open={isNotTailoredModalOpen}
        onClose={() => setIsNotTailoredModalOpen(false)}
        onApply={handleApplyBase}
        onTailorThenApply={handleTailorThenApply}
      />
    </>
  );
}

/** Props for one jobs table row. */
interface JobRowProps {
  /** Data row model. */
  readonly row: JobsRowModel;
  /** Whether row detail panel is open. */
  readonly expanded: boolean;
  /** Whether row has keyboard focus. */
  readonly focused: boolean;
  /** Toggle callback. */
  readonly onToggle: () => void;
}

/**
 * Render one jobs table row and optional expanded detail panel.
 *
 * @param props - {@link JobRowProps}
 * @returns One row and optional expanded detail row.
 */
function JobRow({ row, expanded, focused, onToggle }: JobRowProps): JSX.Element {
  const safeJobPostingUrl = toSafeJobPostingUrl(row.jobPostingUrl);

  return (
    <>
      <tr
        className="border-t transition-colors cursor-pointer"
        style={{
          borderColor: `${COLOR_OUTLINE_VARIANT}20`,
          backgroundColor: focused
            ? COLOR_PRIMARY_FIXED
            : expanded
              ? COLOR_SURFACE_CONTAINER_LOW
              : "transparent",
        }}
        onClick={onToggle}
      >
        <td className="px-5 py-3.5 font-semibold text-sm" style={{ color: COLOR_ON_SURFACE }}>
          {row.company}
        </td>
        <td className="px-5 py-3.5 text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {row.position}
        </td>
        <td className="px-5 py-3.5 text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {row.location}
        </td>
        <td className="px-5 py-3.5">
          <span
            className={`rounded-lg px-2 py-0.5 text-[10px] font-bold tracking-wider ${sourceBadgeClass(row.source)}`}
          >
            {row.source}
          </span>
        </td>
        <td className="px-5 py-3.5">
          <span
            className={`rounded-lg px-2 py-0.5 text-[10px] font-bold tracking-wider ${statusBadgeClass(row.status)}`}
          >
            {row.status}
          </span>
        </td>
        <td className="px-5 py-3.5 text-xs" style={{ color: COLOR_OUTLINE }}>
          {formatDiscovered(row.discovered)}
        </td>
        <td className="px-5 py-3.5 text-right">
          <span
            className="material-symbols-outlined text-[18px] transition-transform"
            style={{
              color: COLOR_PRIMARY,
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            }}
          >
            expand_more
          </span>
        </td>
      </tr>

      {expanded && (
        <tr style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}>
          <td className="px-5 py-5" colSpan={7}>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="space-y-2">
                <p
                  className="text-[10px] uppercase tracking-widest font-bold"
                  style={{ color: COLOR_OUTLINE }}
                >
                  Gate Verdict
                </p>
                <p className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE }}>
                  {row.gateVerdict}
                </p>
                <p className="text-xs leading-5" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  {row.gateReasoning}
                </p>
                {safeJobPostingUrl !== null ? (
                  <a
                    className="inline-flex items-center gap-1 text-xs font-semibold hover:underline"
                    href={safeJobPostingUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: COLOR_PRIMARY }}
                  >
                    View Job Posting
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                  </a>
                ) : (
                  <p className="text-xs font-semibold" style={{ color: COLOR_OUTLINE }}>
                    Job posting URL unavailable
                  </p>
                )}
              </div>

              <div className="space-y-2 lg:col-span-2">
                <p
                  className="text-[10px] uppercase tracking-widest font-bold"
                  style={{ color: COLOR_OUTLINE }}
                >
                  Pipeline
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {row.pipeline.map((step) => (
                    <div
                      key={step.label}
                      className="rounded-lg border px-3 py-2 text-xs"
                      style={{ borderColor: `${COLOR_OUTLINE_VARIANT}40` }}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            step.status === "complete"
                              ? "bg-success"
                              : step.status === "active"
                                ? "bg-primary"
                                : "bg-surface-container-high"
                          }`}
                        />
                        <span className="font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                          {step.label}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <TailoredResumeCell row={row} />
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
  /** Total items across all pages. */
  readonly totalItems: number;
  /** Page-change callback. */
  readonly onPageChange: (page: number) => void;
}

/**
 * Render table pagination controls.
 *
 * @param props - {@link PaginationProps}
 * @returns Pagination footer row.
 */
function Pagination({
  currentPage,
  totalPages,
  totalItems,
  onPageChange,
}: PaginationProps): JSX.Element {
  const safeTotalPages = Math.max(1, totalPages);

  return (
    <div
      className="px-5 py-3.5 border-t flex items-center justify-between"
      style={{ borderColor: `${COLOR_OUTLINE_VARIANT}20` }}
    >
      <p className="text-xs font-medium" style={{ color: COLOR_OUTLINE }}>
        Page {currentPage} of {safeTotalPages} ({totalItems.toLocaleString()} jobs)
      </p>
      <div className="flex items-center gap-2">
        <button
          className="rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40"
          style={{
            borderColor: COLOR_OUTLINE_VARIANT,
            color: COLOR_ON_SURFACE_VARIANT,
          }}
          onClick={() => {
            onPageChange(Math.max(1, currentPage - 1));
          }}
          disabled={currentPage <= 1}
        >
          Prev
        </button>
        <button
          className="rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40"
          style={{
            borderColor: COLOR_OUTLINE_VARIANT,
            color: COLOR_ON_SURFACE_VARIANT,
          }}
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
