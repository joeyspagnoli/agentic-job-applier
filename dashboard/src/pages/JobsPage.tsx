/**
 * @packageDocumentation
 *
 * Jobs dashboard page with server-backed filtering, pagination, and expandable rows.
 */

import type { ChangeEvent, JSX } from "react";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toJobsRows, type JobsRowModel } from "@/lib/api/adapters";
import { fetchJobs, getTailoredResumeUrl } from "@/lib/api/client";
import { COLOR_OUTLINE_VARIANT, COLOR_PRIMARY, COLOR_SURFACE_CONTAINER_LOW } from "@/lib/design-tokens";
import { toSafeJobPostingUrl } from "@/pages/jobs-url";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

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
  if (source === "GREENHOUSE") {
    return "bg-indigo-100 text-indigo-700";
  }
  if (source === "WORKDAY") {
    return "bg-emerald-100 text-emerald-700";
  }
  return "bg-slate-100 text-slate-700";
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
    return "bg-green-100 text-green-700";
  }
  if (normalized.includes("PENDING")) {
    return "bg-amber-100 text-amber-700";
  }
  if (normalized.includes("FAILED")) {
    return "bg-red-100 text-red-700";
  }
  if (normalized === "FILTERED" || normalized === "REJECTED") {
    return "bg-slate-100 text-slate-700";
  }
  return "bg-indigo-100 text-indigo-700";
}

/**
 * Jobs dashboard page component.
 *
 * @returns The full page content rendered inside AppLayout.
 */
export function JobsPage(): JSX.Element {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

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
      },
    ],
    queryFn: () =>
      fetchJobs({
        search: debouncedSearchQuery,
        status: statusFilter,
        source: sourceFilter,
        page: currentPage,
        pageSize: PAGE_SIZE,
      }),
  });

  const rows = jobsQuery.data ? toJobsRows(jobsQuery.data) : [];
  const totalItems = jobsQuery.data?.total_items ?? 0;
  const totalPages = jobsQuery.data?.total_pages ?? 1;

  const qualifiedCount = rows.filter((row) => row.status === "QUALIFIED").length;
  const filteredCount = rows.filter((row) => row.status === "FILTERED").length;
  const inProgressCount = rows.filter(
    (row) => !["APPLIED", "REJECTED", "FILTERED"].includes(row.status),
  ).length;

  function handleSearchChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
    setCurrentPage(1);
  }

  function handleStatusChange(event: ChangeEvent<HTMLSelectElement>): void {
    setStatusFilter(event.target.value);
    setCurrentPage(1);
  }

  function handleSourceChange(event: ChangeEvent<HTMLSelectElement>): void {
    setSourceFilter(event.target.value);
    setCurrentPage(1);
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard label="TOTAL JOBS" value={totalItems.toLocaleString()} subtitle="All discovered jobs" />
        <StatCard label="QUALIFIED" value={qualifiedCount.toLocaleString()} subtitle="On this page" />
        <StatCard label="FILTERED" value={filteredCount.toLocaleString()} subtitle="On this page" />
        <StatCard label="IN PROGRESS" value={inProgressCount.toLocaleString()} subtitle="On this page" />
      </div>

      <div className="bg-white p-4 rounded-xl border border-white flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="relative md:w-[420px]">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
            search
          </span>
          <input
            className="w-full rounded-lg border bg-slate-50 py-2 pl-10 pr-3 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            placeholder="Search company or role..."
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </div>

        <div className="flex gap-3">
          <select
            className="rounded-lg border bg-white px-3 py-2 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            value={statusFilter}
            onChange={handleStatusChange}
          >
            <option value="">All Statuses</option>
            <option value="QUALIFIED">QUALIFIED</option>
            <option value="FILTERED">FILTERED</option>
            <option value="APPLIED">APPLIED</option>
            <option value="REJECTED">REJECTED</option>
          </select>

          <select
            className="rounded-lg border bg-white px-3 py-2 text-sm"
            style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66` }}
            value={sourceFilter}
            onChange={handleSourceChange}
          >
            <option value="">All Sources</option>
            <option value="GREENHOUSE">GREENHOUSE</option>
            <option value="WORKDAY">WORKDAY</option>
            <option value="JOBSPY">JOBSPY</option>
          </select>
        </div>
      </div>

      {jobsQuery.isError && (
        <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load jobs table data. Use Sync now to retry.
        </div>
      )}

      <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-white">
        <table className="w-full text-left border-collapse">
          <thead style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}>
            <tr>
              {["COMPANY", "POSITION", "LOCATION", "PAY", "TYPE", "SOURCE", "STATUS", "DISCOVERED", ""].map((heading) => (
                <th
                  key={heading}
                  className="px-6 py-4 text-[10px] font-bold tracking-widest uppercase"
                  style={{ textAlign: heading === "" ? "right" : "left" }}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <JobRow
                key={row.id}
                row={row}
                expanded={expandedRowId === row.id}
                onToggle={() => {
                  setExpandedRowId((previous) => (previous === row.id ? null : row.id));
                }}
              />
            ))}
            {jobsQuery.isLoading && (
              <tr>
                <td className="px-6 py-10 text-sm text-slate-500" colSpan={9}>
                  Loading jobs...
                </td>
              </tr>
            )}
            {!jobsQuery.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-6 py-10 text-sm text-slate-500" colSpan={9}>
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
          }}
        />
      </div>
    </div>
  );
}

/** Props for compact top-level stat cards. */
interface StatCardProps {
  /** Card label text. */
  readonly label: string;
  /** Card value text. */
  readonly value: string;
  /** Card subtitle text. */
  readonly subtitle: string;
}

/**
 * Render one jobs KPI card.
 *
 * @param props - {@link StatCardProps}
 * @returns One KPI card element.
 */
function StatCard({ label, value, subtitle }: StatCardProps): JSX.Element {
  return (
    <div className="rounded-xl bg-white border border-white p-6 shadow-sm">
      <p className="text-[11px] font-bold tracking-widest uppercase text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-black text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
    </div>
  );
}

/** Props for one jobs table row. */
interface JobRowProps {
  /** Data row model. */
  readonly row: JobsRowModel;
  /** Whether row detail panel is open. */
  readonly expanded: boolean;
  /** Toggle callback. */
  readonly onToggle: () => void;
}

/**
 * Render one jobs table row and optional expanded detail panel.
 *
 * @param props - {@link JobRowProps}
 * @returns One row and optional expanded detail row.
 */
function JobRow({ row, expanded, onToggle }: JobRowProps): JSX.Element {
  const safeJobPostingUrl = toSafeJobPostingUrl(row.jobPostingUrl);

  return (
    <>
      <tr className="border-t border-slate-100 hover:bg-slate-50/50 transition-colors">
        <td className="px-6 py-4 font-semibold text-slate-900">{row.company}</td>
        <td className="px-6 py-4 text-slate-700">{row.position}</td>
        <td className="px-6 py-4 text-slate-600">{row.location}</td>
        <td className="px-6 py-4 text-slate-600">{row.pay}</td>
        <td className="px-6 py-4 text-slate-600">{row.workType}</td>
        <td className="px-6 py-4">
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider ${sourceBadgeClass(row.source)}`}>
            {row.source}
          </span>
        </td>
        <td className="px-6 py-4">
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wider ${statusBadgeClass(row.status)}`}>
            {row.status}
          </span>
        </td>
        <td className="px-6 py-4 text-xs text-slate-500">{formatDiscovered(row.discovered)}</td>
        <td className="px-6 py-4 text-right">
          <button className="p-1" style={{ color: COLOR_PRIMARY }} onClick={onToggle} aria-label="Toggle row details">
            <span className="material-symbols-outlined">{expanded ? "expand_less" : "expand_more"}</span>
          </button>
        </td>
      </tr>

      {expanded && (
        <tr className="bg-slate-50/50">
          <td className="px-6 py-6" colSpan={9}>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-widest font-bold text-slate-500">Gate Verdict</p>
                <p className="text-sm font-semibold text-slate-900">{row.gateVerdict}</p>
                <p className="text-xs text-slate-600 leading-5">{row.gateReasoning}</p>
                {safeJobPostingUrl !== null ? (
                  <a
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 hover:underline"
                    href={safeJobPostingUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View Job Posting
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                  </a>
                ) : (
                  <p className="text-xs font-semibold text-slate-500">Job posting URL unavailable</p>
                )}
              </div>

              <div className="space-y-2 lg:col-span-2">
                <p className="text-[11px] uppercase tracking-widest font-bold text-slate-500">Pipeline</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {row.pipeline.map((step) => (
                    <div key={step.label} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            step.status === "complete"
                              ? "bg-green-500"
                              : step.status === "active"
                                ? "bg-indigo-500"
                                : "bg-slate-300"
                          }`}
                        />
                        <span className="font-semibold text-slate-700">{step.label}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-600">
                  Tailored Resume:{" "}
                  {row.tailoredResume ? (
                    <a
                      className="font-semibold text-indigo-700 hover:underline"
                      href={getTailoredResumeUrl(row.jobHash)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Download PDF
                    </a>
                  ) : (
                    "Not generated yet"
                  )}
                </p>
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
function Pagination({ currentPage, totalPages, totalItems, onPageChange }: PaginationProps): JSX.Element {
  const safeTotalPages = Math.max(1, totalPages);

  return (
    <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between">
      <p className="text-xs font-medium text-slate-500">
        Showing page {currentPage} of {safeTotalPages} ({totalItems.toLocaleString()} jobs)
      </p>
      <div className="flex items-center gap-2">
        <button
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 disabled:opacity-40"
          onClick={() => {
            onPageChange(Math.max(1, currentPage - 1));
          }}
          disabled={currentPage <= 1}
        >
          Prev
        </button>
        <button
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 disabled:opacity-40"
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
