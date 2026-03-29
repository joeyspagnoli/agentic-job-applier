/**
 * @packageDocumentation
 *
 * Jobs dashboard page — all discovered jobs with filtering and expandable
 * row detail panels showing pipeline progress, gate reasoning, and tailored
 * resume artifacts.
 *
 * @remarks
 * All data is hardcoded mock data matching the Stitch HTML reference at
 * `all-html.txt` lines 4122–4801. No API calls are made yet. Expand any
 * row by clicking it to see the pipeline timeline, gate verdict, and resume.
 */

import type { JSX } from "react";
import { useState } from "react";
import {
  COLOR_PRIMARY,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Work arrangement type for a job listing. */
type WorkType = "HYBRID" | "REMOTE" | "IN_PERSON";

/** Source platform from which the job was discovered. */
type JobSource = "GREENHOUSE" | "WORKDAY" | "JOBSPY";

/** Pipeline processing status of a job row. */
type JobStatus =
  | "APPLY_SUCCESS"
  | "REVIEW_PENDING"
  | "TAILOR_PENDING"
  | "QUALIFIED"
  | "FILTERED"
  | "TAILOR_FAILED";

/** Gate classifier verdict. */
type GateVerdict = "APPLY" | "SKIP";

/** Rendering state for one step in the pipeline progress timeline. */
type PipelineStepStatus = "complete" | "active" | "pending";

/** A single node in the pipeline progress timeline. */
interface PipelineStep {
  readonly label: string;
  readonly status: PipelineStepStatus;
}

/** Full data shape for one row in the Jobs table. */
interface JobRow {
  readonly id: number;
  readonly company: string;
  readonly position: string;
  readonly location: string;
  readonly pay: string;
  readonly workType: WorkType;
  readonly source: JobSource;
  readonly status: JobStatus;
  readonly discovered: string;
  readonly pipeline: readonly PipelineStep[];
  readonly gateVerdict: GateVerdict;
  readonly gateReasoning: string;
  /** Null when no tailored resume has been generated for this job yet. */
  readonly tailoredResume: string | null;
  readonly jobPostingUrl: string;
}

// ---------------------------------------------------------------------------
// KPI constants
// ---------------------------------------------------------------------------

const TOTAL_JOBS = 2_847 as const;
const QUALIFIED_COUNT = 847 as const;
const FILTERED_COUNT = 1_612 as const;
const IN_PROGRESS_COUNT = 388 as const;

/** Last page number displayed in the pagination footer. */
const TOTAL_PAGES = 142 as const;

// ---------------------------------------------------------------------------
// Mock pipeline templates
// ---------------------------------------------------------------------------

/** Stripe row: 3 complete, REVIEWED active, rest pending. */
const STRIPE_PIPELINE: readonly PipelineStep[] = [
  { label: "DISCOVERED", status: "complete" },
  { label: "QUALIFIED", status: "complete" },
  { label: "TAILORED", status: "complete" },
  { label: "REVIEWED", status: "active" },
  { label: "APPLIED", status: "pending" },
  { label: "HUMAN REVIEW", status: "pending" },
] as const satisfies readonly PipelineStep[];

// ---------------------------------------------------------------------------
// Mock table data
// ---------------------------------------------------------------------------

const MOCK_JOBS: readonly JobRow[] = [
  {
    id: 1,
    company: "Google",
    position: "Senior Product Designer",
    location: "Mountain View, CA",
    pay: "$180k–$240k",
    workType: "HYBRID",
    source: "GREENHOUSE",
    status: "APPLY_SUCCESS",
    discovered: "2h ago",
    pipeline: [
      { label: "DISCOVERED", status: "complete" },
      { label: "QUALIFIED", status: "complete" },
      { label: "TAILORED", status: "complete" },
      { label: "REVIEWED", status: "complete" },
      { label: "APPLIED", status: "complete" },
      { label: "HUMAN REVIEW", status: "pending" },
    ],
    gateVerdict: "APPLY",
    gateReasoning:
      "Strong portfolio match: extensive UX leadership at scale detected. Candidate's cross-functional collaboration experience aligns with Google's product design expectations.",
    tailoredResume: "google_senior_pd_v1.pdf",
    jobPostingUrl: "#",
  },
  {
    id: 2,
    company: "Stripe",
    position: "Staff Software Engineer",
    location: "San Francisco, CA",
    pay: "$200k–$280k",
    workType: "REMOTE",
    source: "GREENHOUSE",
    status: "REVIEW_PENDING",
    discovered: "5h ago",
    pipeline: STRIPE_PIPELINE,
    gateVerdict: "APPLY",
    gateReasoning:
      "Strong match: 5+ years full-stack experience in fintech environment detected. Candidate's recent work at PayPal perfectly aligns with Stripe's Staff level expectations for infrastructure scaling.",
    tailoredResume: "stripe_staff_swe_v2.pdf",
    jobPostingUrl: "#",
  },
  {
    id: 3,
    company: "Figma",
    position: "Lead Systems Architect",
    location: "New York, NY",
    pay: "$170k–$220k",
    workType: "IN_PERSON",
    source: "WORKDAY",
    status: "TAILOR_PENDING",
    discovered: "Yesterday",
    pipeline: [
      { label: "DISCOVERED", status: "complete" },
      { label: "QUALIFIED", status: "complete" },
      { label: "TAILORED", status: "active" },
      { label: "REVIEWED", status: "pending" },
      { label: "APPLIED", status: "pending" },
      { label: "HUMAN REVIEW", status: "pending" },
    ],
    gateVerdict: "APPLY",
    gateReasoning:
      "Good fit: systems architecture background with distributed systems experience. Role requires senior-level design thinking which candidate has demonstrated.",
    tailoredResume: null,
    jobPostingUrl: "#",
  },
  {
    id: 4,
    company: "Vercel",
    position: "Fullstack Developer",
    location: "—",
    pay: "—",
    workType: "REMOTE",
    source: "JOBSPY",
    status: "QUALIFIED",
    discovered: "Yesterday",
    pipeline: [
      { label: "DISCOVERED", status: "complete" },
      { label: "QUALIFIED", status: "complete" },
      { label: "TAILORED", status: "pending" },
      { label: "REVIEWED", status: "pending" },
      { label: "APPLIED", status: "pending" },
      { label: "HUMAN REVIEW", status: "pending" },
    ],
    gateVerdict: "APPLY",
    gateReasoning:
      "Good match: React and TypeScript expertise clearly demonstrated. Candidate's open-source contributions align with Vercel's developer-focused culture.",
    tailoredResume: null,
    jobPostingUrl: "#",
  },
  {
    id: 5,
    company: "Netflix",
    position: "ML Engineer",
    location: "Los Gatos, CA",
    pay: "$250k–$350k",
    workType: "HYBRID",
    source: "GREENHOUSE",
    status: "FILTERED",
    discovered: "2 days ago",
    pipeline: [
      { label: "DISCOVERED", status: "complete" },
      { label: "QUALIFIED", status: "pending" },
      { label: "TAILORED", status: "pending" },
      { label: "REVIEWED", status: "pending" },
      { label: "APPLIED", status: "pending" },
      { label: "HUMAN REVIEW", status: "pending" },
    ],
    gateVerdict: "SKIP",
    gateReasoning:
      "Insufficient ML/research background. Role requires 5+ years of production ML system experience and PhD-level familiarity with recommendation systems.",
    tailoredResume: null,
    jobPostingUrl: "#",
  },
  {
    id: 6,
    company: "Datadog",
    position: "Backend Engineer",
    location: "—",
    pay: "$160k–$200k",
    workType: "REMOTE",
    source: "JOBSPY",
    status: "TAILOR_FAILED",
    discovered: "3 days ago",
    pipeline: [
      { label: "DISCOVERED", status: "complete" },
      { label: "QUALIFIED", status: "complete" },
      { label: "TAILORED", status: "active" },
      { label: "REVIEWED", status: "pending" },
      { label: "APPLIED", status: "pending" },
      { label: "HUMAN REVIEW", status: "pending" },
    ],
    gateVerdict: "APPLY",
    gateReasoning:
      "Strong fit: Go and distributed systems experience matches Datadog's backend requirements. Candidate's observability work is directly relevant.",
    tailoredResume: null,
    jobPostingUrl: "#",
  },
] as const satisfies readonly JobRow[];

// ---------------------------------------------------------------------------
// Badge styling lookup maps
// ---------------------------------------------------------------------------

/** Tailwind classes for work type pill badges. */
const WORK_TYPE_BADGE_CLASS: Record<WorkType, string> = {
  HYBRID: "bg-amber-50 text-amber-700",
  REMOTE: "bg-green-50 text-green-700",
  IN_PERSON: "bg-slate-100 text-slate-700",
} as const satisfies Record<WorkType, string>;

/** Human-readable labels for work type values. */
const WORK_TYPE_LABEL: Record<WorkType, string> = {
  HYBRID: "Hybrid",
  REMOTE: "Remote",
  IN_PERSON: "In-Person",
} as const satisfies Record<WorkType, string>;

/** Tailwind classes for job source pill badges. */
const SOURCE_BADGE_CLASS: Record<JobSource, string> = {
  GREENHOUSE: "bg-green-50 text-green-700",
  WORKDAY: "bg-blue-50 text-blue-700",
  JOBSPY: "bg-purple-50 text-purple-700",
} as const satisfies Record<JobSource, string>;

/** Human-readable labels for job source values. */
const SOURCE_LABEL: Record<JobSource, string> = {
  GREENHOUSE: "Greenhouse",
  WORKDAY: "Workday",
  JOBSPY: "JobSpy",
} as const satisfies Record<JobSource, string>;

/** Tailwind classes for job status pill badges. */
const STATUS_BADGE_CLASS: Record<JobStatus, string> = {
  APPLY_SUCCESS: "bg-green-100 text-green-800",
  REVIEW_PENDING: "bg-amber-100 text-amber-800",
  TAILOR_PENDING: "bg-amber-100 text-amber-800",
  QUALIFIED: "bg-indigo-100 text-indigo-800",
  FILTERED: "bg-slate-200 text-slate-600",
  TAILOR_FAILED: "bg-red-50 text-red-700",
} as const satisfies Record<JobStatus, string>;

// ---------------------------------------------------------------------------
// Sub-component: JobStatCard
// ---------------------------------------------------------------------------

interface JobStatCardProps {
  readonly icon: string;
  readonly iconClass: string;
  readonly badge: string;
  readonly badgeClass: string;
  readonly value: string;
  readonly valueLabel: string;
  readonly subtitle: string;
  readonly subtitleClass: string;
}

/**
 * One KPI card in the top stat row.
 *
 * @param props - Icon, badge text/color, numeric value, labels, and subtitle.
 * @returns A white rounded stat card.
 */
function JobStatCard({
  icon,
  iconClass,
  badge,
  badgeClass,
  value,
  valueLabel,
  subtitle,
  subtitleClass,
}: JobStatCardProps): JSX.Element {
  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-white">
      <div className="flex items-center justify-between mb-4">
        <span className={`material-symbols-outlined p-2 rounded-lg ${iconClass}`}>{icon}</span>
        <span className={`text-[10px] font-bold tracking-widest uppercase ${badgeClass}`}>
          {badge}
        </span>
      </div>
      <div className="text-3xl font-bold tracking-tight text-[#191c1d] mb-1">{value}</div>
      <div className="text-xs font-medium text-[#464554] tracking-tight">{valueLabel}</div>
      <p className={`text-[10px] mt-1 ${subtitleClass}`}>{subtitle}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: FilterBar
// ---------------------------------------------------------------------------

interface FilterBarProps {
  readonly searchQuery: string;
  readonly onSearchChange: (query: string) => void;
}

/**
 * Search input + three filter dropdown buttons above the jobs table.
 *
 * @param props - Current search query and change handler.
 * @returns The filter bar row.
 */
function FilterBar({ searchQuery, onSearchChange }: FilterBarProps): JSX.Element {
  function handleSearchInput(e: React.ChangeEvent<HTMLInputElement>): void {
    onSearchChange(e.target.value);
  }

  return (
    <div className="flex gap-4 items-center">
      <div className="w-[40%] relative">
        <span
          className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-xl"
          style={{ color: COLOR_OUTLINE_VARIANT }}
        >
          search
        </span>
        <input
          className="w-full rounded-xl pl-12 pr-4 py-3 text-sm outline-none transition-all placeholder:text-[#767586]/50"
          style={{
            backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
            border: "none",
          }}
          placeholder="Search by company, title, or keywords..."
          type="text"
          value={searchQuery}
          onChange={handleSearchInput}
        />
      </div>

      <div className="flex gap-3 ml-auto">
        <button
          className="bg-white px-4 py-3 rounded-xl text-xs font-bold flex items-center gap-4 hover:border-[#4648d4] transition-all"
          style={{ border: `1px solid ${COLOR_OUTLINE_VARIANT}4D`, color: "#464554" }}
        >
          STATUS: ALL STATUSES
          <span className="material-symbols-outlined text-sm">expand_more</span>
        </button>

        <button
          className="bg-white px-4 py-3 rounded-xl text-xs font-bold flex items-center gap-4 hover:border-[#4648d4] transition-all"
          style={{ border: `1px solid ${COLOR_OUTLINE_VARIANT}4D`, color: "#464554" }}
        >
          SOURCE: ALL SOURCES
          <span className="material-symbols-outlined text-sm">expand_more</span>
        </button>

        <button
          className="bg-white px-4 py-3 rounded-xl text-xs font-bold flex items-center gap-4 hover:border-[#4648d4] transition-all"
          style={{ border: `1px solid ${COLOR_OUTLINE_VARIANT}4D`, color: "#464554" }}
        >
          DATE RANGE: LAST 30 DAYS
          <span className="material-symbols-outlined text-sm">calendar_today</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: PipelineTimeline
// ---------------------------------------------------------------------------

interface PipelineTimelineProps {
  readonly steps: readonly PipelineStep[];
}

/**
 * Horizontal pipeline progress timeline with connected step circles.
 *
 * Complete steps render as filled indigo circles with a checkmark.
 * The active step renders as a pulsing outlined indigo circle with a sync icon.
 * Pending steps render as empty gray-outlined circles.
 *
 * @param props - Array of pipeline steps with their render status.
 * @returns The timeline row.
 */
function PipelineTimeline({ steps }: PipelineTimelineProps): JSX.Element {
  const completeCount = steps.filter((s) => s.status === "complete").length;
  // Progress bar covers the segments between complete nodes.
  // e.g. 3 complete out of 6 steps = 3/(6-1) = 60%
  const progressPct = steps.length > 1 ? (completeCount / (steps.length - 1)) * 100 : 0;

  return (
    <div>
      <p
        className="text-[10px] font-bold tracking-widest uppercase mb-6"
        style={{ color: "#464554" }}
      >
        Pipeline Progress
      </p>

      <div className="flex items-center w-full max-w-4xl relative">
        {/* Base gray connector line */}
        <div
          className="absolute top-[18px] left-0 h-0.5 w-full z-0"
          style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}4D` }}
        />
        {/* Filled indigo progress line */}
        <div
          className="absolute top-[18px] left-0 h-0.5 z-0 transition-all"
          style={{
            backgroundColor: COLOR_PRIMARY,
            width: `${progressPct}%`,
          }}
        />

        {steps.map((step) => (
          <div key={step.label} className="relative z-10 flex flex-col items-center flex-1">
            {step.status === "complete" && (
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center mb-2 text-white"
                style={{ backgroundColor: COLOR_PRIMARY }}
              >
                <span
                  className="material-symbols-outlined text-lg"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check
                </span>
              </div>
            )}
            {step.status === "active" && (
              <div
                className="w-9 h-9 bg-white rounded-full flex items-center justify-center mb-2 animate-pulse"
                style={{ border: `4px solid ${COLOR_PRIMARY}`, color: COLOR_PRIMARY }}
              >
                <span className="material-symbols-outlined text-lg">sync</span>
              </div>
            )}
            {step.status === "pending" && (
              <div
                className="w-9 h-9 bg-white rounded-full flex items-center justify-center mb-2"
                style={{ border: `2px solid ${COLOR_OUTLINE_VARIANT}80` }}
              />
            )}

            <span
              className="text-[10px] font-bold tracking-tight"
              style={{
                color:
                  step.status === "active"
                    ? COLOR_PRIMARY
                    : step.status === "pending"
                      ? `${COLOR_OUTLINE_VARIANT}66`
                      : "#191c1d",
              }}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: GateReasoningCard
// ---------------------------------------------------------------------------

interface GateReasoningCardProps {
  readonly verdict: GateVerdict;
  readonly reasoning: string;
}

/**
 * Left panel in an expanded row showing the gate classifier verdict and
 * reasoning text.
 *
 * @param props - Gate verdict (APPLY or SKIP) and the reasoning string.
 * @returns A white rounded card.
 */
function GateReasoningCard({ verdict, reasoning }: GateReasoningCardProps): JSX.Element {
  const verdictBadgeClass =
    verdict === "APPLY" ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-700";
  const verdictLabel = verdict === "APPLY" ? "APPLY VERDICT" : "SKIP VERDICT";

  // Bold the first sentence of reasoning for emphasis.
  const [firstSentence, ...rest] = reasoning.split(": ");
  const hasColon = reasoning.includes(": ");

  return (
    <div className="bg-white p-6 rounded-xl border border-indigo-100">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-xs font-bold flex items-center gap-2" style={{ color: "#464554" }}>
          <span className="material-symbols-outlined" style={{ color: COLOR_PRIMARY }}>
            psychology
          </span>
          Gate Reasoning
        </h4>
        <span
          className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase ${verdictBadgeClass}`}
        >
          {verdictLabel}
        </span>
      </div>

      <p className="text-sm leading-relaxed" style={{ color: "#464554" }}>
        {hasColon ? (
          <>
            <strong className="text-[#191c1d]">{firstSentence}:</strong> {rest.join(": ")}
          </>
        ) : (
          reasoning
        )}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: TailoredResumeCard
// ---------------------------------------------------------------------------

interface TailoredResumeCardProps {
  readonly filename: string | null;
  readonly jobPostingUrl: string;
  readonly onDownload: () => void;
}

/**
 * Right panel in an expanded row showing the tailored resume filename with a
 * download button and a "VIEW JOB POSTING" link.
 *
 * @param props - Resume filename (null if not yet generated), posting URL,
 *   and download callback.
 * @returns A card with resume info and external link.
 */
function TailoredResumeCard({
  filename,
  jobPostingUrl,
  onDownload,
}: TailoredResumeCardProps): JSX.Element {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-4 bg-white rounded-xl border border-indigo-100">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined" style={{ color: COLOR_PRIMARY }}>
            description
          </span>
          <div>
            <p className="text-xs font-bold text-[#191c1d]">Tailored Resume</p>
            <p className="text-[10px]" style={{ color: "#464554" }}>
              {filename ?? "Not yet generated"}
            </p>
          </div>
        </div>
        {filename !== null && (
          <button
            className="p-2 rounded-lg transition-all hover:bg-indigo-50"
            style={{ color: COLOR_PRIMARY }}
            onClick={onDownload}
          >
            <span className="material-symbols-outlined">download</span>
          </button>
        )}
      </div>

      <a
        href={jobPostingUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center gap-2 w-full p-4 rounded-xl text-xs font-bold transition-all hover:bg-[#edeeef]"
        style={{
          backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
          color: "#4648d4",
        }}
      >
        VIEW JOB POSTING
        <span className="material-symbols-outlined text-sm">open_in_new</span>
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: ExpandedRowDetail
// ---------------------------------------------------------------------------

interface ExpandedRowDetailProps {
  readonly job: JobRow;
  readonly onDismiss: (id: number) => void;
  readonly onViewApplication: (id: number) => void;
  readonly onDownloadResume: (id: number) => void;
}

/**
 * Full-width detail panel rendered below an expanded table row.
 *
 * Contains the pipeline timeline, gate reasoning card, tailored resume card,
 * and row action buttons.
 *
 * @param props - The job data and event callbacks.
 * @returns A `<tr>` containing the expanded content spanning all columns.
 */
function ExpandedRowDetail({
  job,
  onDismiss,
  onViewApplication,
  onDownloadResume,
}: ExpandedRowDetailProps): JSX.Element {
  function handleDismiss(): void {
    onDismiss(job.id);
  }

  function handleViewApplication(): void {
    onViewApplication(job.id);
  }

  function handleDownloadResume(): void {
    onDownloadResume(job.id);
  }

  return (
    <tr className="border-b border-[#f3f4f5]/50" style={{ backgroundColor: `${COLOR_PRIMARY}08` }}>
      <td className="p-0" colSpan={9}>
        <div className="px-12 py-8 space-y-8">
          {/* Pipeline progress timeline */}
          <PipelineTimeline steps={job.pipeline} />

          {/* Gate reasoning + tailored resume */}
          <div className="grid grid-cols-2 gap-12">
            <GateReasoningCard verdict={job.gateVerdict} reasoning={job.gateReasoning} />
            <TailoredResumeCard
              filename={job.tailoredResume}
              jobPostingUrl={job.jobPostingUrl}
              onDownload={handleDownloadResume}
            />
          </div>

          {/* Row action buttons */}
          <div className="flex gap-3 pt-2">
            <button
              className="px-5 py-2 rounded-lg text-xs font-bold border transition-all hover:bg-[#f3f4f5]"
              style={{
                borderColor: `${COLOR_OUTLINE_VARIANT}80`,
                color: "#464554",
              }}
              onClick={handleDismiss}
            >
              Dismiss
            </button>
            <button
              className="px-5 py-2 rounded-lg text-xs font-bold text-white transition-all hover:opacity-90"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={handleViewApplication}
            >
              View Application
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: JobTableRow
// ---------------------------------------------------------------------------

interface JobTableRowProps {
  readonly job: JobRow;
  readonly isExpanded: boolean;
  readonly onToggle: (id: number) => void;
  readonly onDismiss: (id: number) => void;
  readonly onViewApplication: (id: number) => void;
  readonly onDownloadResume: (id: number) => void;
}

/**
 * One job row in the table, plus its optional expanded detail panel.
 *
 * Clicking the row (or the chevron button) toggles the expanded state.
 *
 * @param props - Job data, expansion state, and event callbacks.
 * @returns Two `<tr>` elements (main row + conditional detail row).
 */
function JobTableRow({
  job,
  isExpanded,
  onToggle,
  onDismiss,
  onViewApplication,
  onDownloadResume,
}: JobTableRowProps): JSX.Element {
  function handleRowClick(): void {
    onToggle(job.id);
  }

  return (
    <>
      <tr
        className="transition-colors border-b border-[#f3f4f5]/50 cursor-pointer"
        style={{
          backgroundColor: isExpanded ? `${COLOR_PRIMARY}08` : undefined,
          borderLeft: isExpanded ? `4px solid ${COLOR_PRIMARY}` : "4px solid transparent",
        }}
        onClick={handleRowClick}
      >
        <td className="px-6 py-4 font-bold text-sm text-[#191c1d]">{job.company}</td>
        <td className="px-6 py-4 text-sm" style={{ color: "#464554" }}>
          {job.position}
        </td>
        <td className="px-6 py-4 text-sm" style={{ color: "#464554" }}>
          {job.location}
        </td>
        <td className="px-6 py-4 text-sm" style={{ color: "#464554" }}>
          {job.pay}
        </td>
        <td className="px-6 py-4">
          <span
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${WORK_TYPE_BADGE_CLASS[job.workType]}`}
          >
            {WORK_TYPE_LABEL[job.workType]}
          </span>
        </td>
        <td className="px-6 py-4">
          <span
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${SOURCE_BADGE_CLASS[job.source]}`}
          >
            {SOURCE_LABEL[job.source]}
          </span>
        </td>
        <td className="px-6 py-4">
          <span
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${STATUS_BADGE_CLASS[job.status]}`}
          >
            {job.status}
          </span>
        </td>
        <td className="px-6 py-4 text-[11px]" style={{ color: "#464554" }}>
          {job.discovered}
        </td>
        <td className="px-6 py-4 text-right">
          <button
            className="p-2 rounded-lg transition-all"
            style={{ color: isExpanded ? COLOR_PRIMARY : undefined }}
            onClick={handleRowClick}
          >
            <span className="material-symbols-outlined">
              {isExpanded ? "expand_less" : "more_vert"}
            </span>
          </button>
        </td>
      </tr>

      {isExpanded && (
        <ExpandedRowDetail
          job={job}
          onDismiss={onDismiss}
          onViewApplication={onViewApplication}
          onDownloadResume={onDownloadResume}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: PaginationBar
// ---------------------------------------------------------------------------

interface PaginationBarProps {
  readonly currentPage: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}

/**
 * Pagination footer showing "SHOWING 1-20 OF N JOBS" and page number buttons.
 *
 * Renders pages 1–3, an ellipsis, and the last page. Cosmetic only — the
 * table data does not change (all mocked).
 *
 * @param props - Current page, total pages, and page-change callback.
 * @returns The pagination row.
 */
function PaginationBar({ currentPage, totalPages, onPageChange }: PaginationBarProps): JSX.Element {
  function handlePrev(): void {
    if (currentPage > 1) onPageChange(currentPage - 1);
  }

  function handleNext(): void {
    if (currentPage < totalPages) onPageChange(currentPage + 1);
  }

  function handlePage(page: number): void {
    onPageChange(page);
  }

  /** Visible page numbers: always show 1, 2, 3, then last page. */
  const VISIBLE_PAGES = [1, 2, 3] as const;

  return (
    <div
      className="px-6 py-6 border-t flex justify-between items-center bg-white"
      style={{ borderColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}
    >
      <p className="text-[11px] font-bold tracking-wider uppercase" style={{ color: "#464554" }}>
        Showing 1–20 of {TOTAL_JOBS.toLocaleString()} jobs
      </p>

      <div className="flex gap-1">
        <button
          className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:bg-[#edeeef]"
          style={{ color: "#464554" }}
          onClick={handlePrev}
          disabled={currentPage === 1}
        >
          <span className="material-symbols-outlined text-lg">chevron_left</span>
        </button>

        {VISIBLE_PAGES.map((page) => (
          <button
            key={page}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold transition-all"
            style={
              currentPage === page
                ? { backgroundColor: COLOR_PRIMARY, color: "#ffffff" }
                : { color: "#464554" }
            }
            onClick={() => handlePage(page)}
          >
            {page}
          </button>
        ))}

        <span
          className="w-8 h-8 flex items-center justify-center text-xs"
          style={{ color: "#464554" }}
        >
          ...
        </span>

        <button
          className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold transition-all hover:bg-[#edeeef]"
          style={{ color: "#464554" }}
          onClick={() => handlePage(totalPages)}
        >
          {totalPages}
        </button>

        <button
          className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:bg-[#edeeef]"
          style={{ color: "#464554" }}
          onClick={handleNext}
          disabled={currentPage === totalPages}
        >
          <span className="material-symbols-outlined text-lg">chevron_right</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

/**
 * Jobs dashboard page component.
 *
 * Renders 4 KPI stat cards, a search/filter bar, a jobs data table with
 * expandable rows, and a pagination footer.
 *
 * @returns The full page content rendered inside AppLayout.
 */
export function JobsPage(): JSX.Element {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  function handleSearchChange(query: string): void {
    setSearchQuery(query);
  }

  function handleRowToggle(id: number): void {
    setExpandedRowId((prev) => (prev === id ? null : id));
  }

  function handleDismiss(id: number): void {
    console.info(`[JobsPage] Dismiss requested for job id=${id}`);
  }

  function handleViewApplication(id: number): void {
    console.info(`[JobsPage] View application requested for job id=${id}`);
  }

  function handleDownloadResume(id: number): void {
    console.info(`[JobsPage] Download resume requested for job id=${id}`);
  }

  function handlePageChange(page: number): void {
    setCurrentPage(page);
  }

  // Client-side search filter — matches company or position (case-insensitive).
  const trimmedQuery = searchQuery.trim().toLowerCase();
  const visibleJobs =
    trimmedQuery.length === 0
      ? MOCK_JOBS
      : MOCK_JOBS.filter(
          (job) =>
            job.company.toLowerCase().includes(trimmedQuery) ||
            job.position.toLowerCase().includes(trimmedQuery),
        );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* ------------------------------------------------------------------ */}
      {/* Row 1 — KPI stat cards                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <JobStatCard
          icon="database"
          iconClass="text-[#4648d4] bg-indigo-50"
          badge="Overview"
          badgeClass="text-[#464554]"
          value={TOTAL_JOBS.toLocaleString()}
          valueLabel="TOTAL JOBS"
          subtitle="All discovered jobs"
          subtitleClass="text-[#464554]/60"
        />
        <JobStatCard
          icon="check_circle"
          iconClass="text-green-600 bg-green-50"
          badge="+12%"
          badgeClass="text-green-700"
          value={QUALIFIED_COUNT.toLocaleString()}
          valueLabel="QUALIFIED"
          subtitle="Passed gate filter"
          subtitleClass="text-green-600"
        />
        <JobStatCard
          icon="filter_alt"
          iconClass="text-amber-600 bg-amber-50"
          badge="Auto-Action"
          badgeClass="text-amber-700"
          value={FILTERED_COUNT.toLocaleString()}
          valueLabel="FILTERED"
          subtitle="Skipped by gate"
          subtitleClass="text-[#464554]/60"
        />
        <JobStatCard
          icon="hourglass_empty"
          iconClass="text-indigo-600 bg-indigo-50"
          badge="Active"
          badgeClass="text-indigo-700"
          value={IN_PROGRESS_COUNT.toLocaleString()}
          valueLabel="IN PROGRESS"
          subtitle="Currently in pipeline"
          subtitleClass="text-indigo-600"
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Row 2 — Filter bar                                                  */}
      {/* ------------------------------------------------------------------ */}
      <FilterBar searchQuery={searchQuery} onSearchChange={handleSearchChange} />

      {/* ------------------------------------------------------------------ */}
      {/* Row 3 — Jobs data table                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-white">
        <table className="w-full text-left border-collapse">
          <thead style={{ backgroundColor: `${COLOR_SURFACE_CONTAINER_LOW}80` }}>
            <tr>
              {[
                "COMPANY",
                "POSITION",
                "LOCATION",
                "PAY",
                "TYPE",
                "SOURCE",
                "STATUS",
                "DISCOVERED",
                "",
              ].map((heading) => (
                <th
                  key={heading}
                  className="px-6 py-4 text-[10px] font-bold tracking-widest uppercase text-right last:text-right"
                  style={{
                    color: "#464554",
                    textAlign: heading === "" ? "right" : "left",
                  }}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="text-sm">
            {visibleJobs.map((job) => (
              <JobTableRow
                key={job.id}
                job={job}
                isExpanded={expandedRowId === job.id}
                onToggle={handleRowToggle}
                onDismiss={handleDismiss}
                onViewApplication={handleViewApplication}
                onDownloadResume={handleDownloadResume}
              />
            ))}
          </tbody>
        </table>

        <PaginationBar
          currentPage={currentPage}
          totalPages={TOTAL_PAGES}
          onPageChange={handlePageChange}
        />
      </div>
    </div>
  );
}
