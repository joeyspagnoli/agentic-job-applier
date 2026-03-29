/**
 * @packageDocumentation
 *
 * Human Review page — displays applications flagged for manual verification.
 *
 * @remarks
 * Each record shows why the agent's automation halted ("Why Flagged") and
 * AI-recommended answers for every form field the agent could not fill
 * automatically. The Application Capture screenshot is intentionally omitted
 * in favour of this actionable answer panel.
 *
 * All data is currently hardcoded mock values matching the Stitch design
 * mockup. Replace each constant with an API call once the FastAPI backend
 * is wired up.
 */

import type { JSX } from "react";
import { useState } from "react";
import { COLOR_PRIMARY, COLOR_PRIMARY_CONTAINER, COLOR_OUTLINE_VARIANT } from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Local color constants — page-specific, not in design-tokens.ts
// ---------------------------------------------------------------------------

/** emerald-500 — confidence dot for scores ≥ 80 %. */
const COLOR_EMERALD_DOT = "#10b981" as const;

/** amber-500 — confidence dot for scores 60–79 %. */
const COLOR_AMBER_DOT = "#f59e0b" as const;

/** rose-500 — confidence dot for scores < 60 %. */
const COLOR_ROSE_DOT = "#f43f5e" as const;

/** emerald-600 — confidence text for scores ≥ 80 %. */
const COLOR_EMERALD_TEXT = "#059669" as const;

/** amber-600 — confidence text for scores 60–79 %. */
const COLOR_AMBER_TEXT = "#d97706" as const;

/** rose-600 — confidence text for scores < 60 %. */
const COLOR_ROSE_TEXT = "#e11d48" as const;

/** Minimum integer percentage classified as "high confidence" (green). */
const CONFIDENCE_HIGH_THRESHOLD = 80 as const;

/** Minimum integer percentage classified as "medium confidence" (amber). */
const CONFIDENCE_MEDIUM_THRESHOLD = 60 as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Possible status values shown in the Status column. */
type ReviewStatus = "NEEDS_REVIEW" | "REVIEWED";

/** How confident the AI is in a specific recommended answer. */
type AnswerConfidence = "high" | "medium" | "low";

/**
 * A single form field the agent could not complete automatically,
 * paired with an AI-generated suggested answer.
 */
interface UnresolvedField {
  readonly fieldName: string;
  readonly aiAnswer: string;
  /** One-sentence explanation of how/why this answer was generated. */
  readonly reasoning: string;
  readonly answerConfidence: AnswerConfidence;
}

/** A single entry in the human review queue. */
interface ReviewRecord {
  readonly id: number;
  /** Single letter rendered inside the company avatar circle. */
  readonly companyInitial: string;
  readonly companyName: string;
  /** Tailwind bg class for the company avatar (e.g. `"bg-indigo-500"`). */
  readonly avatarBgClass: string;
  /** Tailwind text class for the company avatar letter (e.g. `"text-white"`). */
  readonly avatarTextClass: string;
  readonly position: string;
  readonly status: ReviewStatus;
  /** Automation confidence as an integer percentage (0–100). */
  readonly confidencePct: number;
  readonly appliedDate: string;
  /** Agent-generated explanation of why automation was halted. */
  readonly agentDiagnostic: string;
  readonly jobPostingUrl: string;
  readonly resumeFileName: string;
  readonly unresolvedFields: readonly UnresolvedField[];
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const REVIEW_RECORDS: readonly ReviewRecord[] = [
  {
    id: 1,
    companyInitial: "G",
    companyName: "Google",
    avatarBgClass: "bg-surface-container-high",
    avatarTextClass: "text-on-surface-variant",
    position: "Senior Product Designer",
    status: "NEEDS_REVIEW",
    confidencePct: 84,
    appliedDate: "2 hours ago",
    agentDiagnostic:
      "Automation stopped at Step 6: Portfolio Submission. The form requires a personal portfolio URL not found in candidate_profile.yaml. Halted to avoid submitting an incomplete application.",
    jobPostingUrl: "#",
    resumeFileName: "google_designer_v2.pdf",
    unresolvedFields: [
      {
        fieldName: "Portfolio / Work Samples URL",
        aiAnswer: "https://portfolio.example.com",
        reasoning:
          "No portfolio URL found in candidate_profile.yaml. Replace this placeholder with your actual portfolio link before submitting.",
        answerConfidence: "low",
      },
      {
        fieldName: "Desired Start Date",
        aiAnswer: "2 weeks after offer acceptance",
        reasoning:
          "Standard two-week notice period inferred. No preferred start date in profile — update if you have specific constraints.",
        answerConfidence: "medium",
      },
    ],
  },
  {
    id: 2,
    companyInitial: "S",
    companyName: "Stripe",
    avatarBgClass: "bg-indigo-500",
    avatarTextClass: "text-white",
    position: "Staff Software Engineer",
    status: "NEEDS_REVIEW",
    confidencePct: 62,
    appliedDate: "5 hours ago",
    agentDiagnostic:
      "Automation stopped at Step 4: Salary Expectations. The field is a free-text input requiring a specific dollar range. Estimated range: $180k–$220k. Requesting human confirmation before proceeding.",
    jobPostingUrl: "#",
    resumeFileName: "stripe_v2.pdf",
    unresolvedFields: [
      {
        fieldName: "Salary Expectations",
        aiAnswer: "$185,000 – $210,000",
        reasoning:
          "Based on Levels.fyi data for Staff SWE in the SF Bay Area with 8 years of experience. Sits at mid-range of reported P5/Staff compensation.",
        answerConfidence: "high",
      },
      {
        fieldName: "Will you require visa sponsorship now or in the future?",
        aiAnswer: "No",
        reasoning:
          "Candidate profile indicates permanent work authorization. No sponsorship required.",
        answerConfidence: "high",
      },
      {
        fieldName: "How did you hear about this role?",
        aiAnswer: "Via a job aggregator",
        reasoning:
          "Discovered via the JobSpy automated pipeline. Recommend replacing with a more personal answer before submitting.",
        answerConfidence: "low",
      },
    ],
  },
  {
    id: 3,
    companyInitial: "F",
    companyName: "Figma",
    avatarBgClass: "bg-surface-container-high",
    avatarTextClass: "text-on-surface-variant",
    position: "Lead Systems Architect",
    status: "NEEDS_REVIEW",
    confidencePct: 38,
    appliedDate: "Yesterday",
    agentDiagnostic:
      "Automation stopped at Step 2: Screening questions. Five open-ended questions require detailed personal responses that fall below the confidence threshold (< 40%). All fields flagged for manual review.",
    jobPostingUrl: "#",
    resumeFileName: "figma_architect_v1.pdf",
    unresolvedFields: [
      {
        fieldName: "Describe a large-scale system you designed from scratch",
        aiAnswer:
          "Led architecture for a distributed event-sourcing platform handling 50k events/sec. Used Kafka, PostgreSQL read replicas, and Go microservices. Reduced P99 latency by 40% over 6 months.",
        reasoning:
          "Synthesised from resume bullet points. Verify accuracy and expand with project-specific details before submitting.",
        answerConfidence: "medium",
      },
      {
        fieldName: "Why Figma specifically?",
        aiAnswer:
          "Figma's real-time collaboration engine is one of the most technically impressive systems in production. I'm excited by the challenge of scaling design infrastructure at a product-led growth company.",
        reasoning:
          "Generic answer — strongly recommend personalising with specific Figma products or engineering blog posts you've read.",
        answerConfidence: "low",
      },
      {
        fieldName: "Expected compensation range",
        aiAnswer: "$220,000 – $260,000",
        reasoning:
          "Based on Figma L6/Staff Architect band estimates. High uncertainty due to limited public data for this title.",
        answerConfidence: "medium",
      },
      {
        fieldName: "Earliest available start date",
        aiAnswer: "Available in 2–3 weeks",
        reasoning:
          "Inferred from standard notice period. Update if you have specific scheduling constraints.",
        answerConfidence: "medium",
      },
      {
        fieldName: "Comfortable with occasional on-site requirements (San Francisco)?",
        aiAnswer: "Yes",
        reasoning:
          "No remote-only constraint found in candidate profile. Confirm this matches your situation.",
        answerConfidence: "high",
      },
    ],
  },
  {
    id: 4,
    companyInitial: "V",
    companyName: "Vercel",
    avatarBgClass: "bg-black",
    avatarTextClass: "text-white",
    position: "Fullstack Developer",
    status: "REVIEWED",
    confidencePct: 92,
    appliedDate: "Oct 12",
    agentDiagnostic:
      "Application completed with high confidence. All required fields answered automatically. LinkedIn profile URL was auto-filled from candidate_profile.yaml. No manual intervention was required.",
    jobPostingUrl: "#",
    resumeFileName: "vercel_fullstack_v3.pdf",
    unresolvedFields: [],
  },
] as const satisfies readonly ReviewRecord[];

/** Column header labels for the data table. */
const TABLE_COLUMNS = [
  "Company",
  "Position",
  "Status",
  "Confidence",
  "Applied Date",
  "Actions",
] as const;

/** Styling config for each AnswerConfidence tier. */
const ANSWER_CONFIDENCE_STYLE: Record<
  AnswerConfidence,
  { readonly badgeClass: string; readonly label: string }
> = {
  high: {
    badgeClass: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    label: "High confidence",
  },
  medium: {
    badgeClass: "bg-amber-50 text-amber-700 border border-amber-200",
    label: "Medium confidence",
  },
  low: {
    badgeClass: "bg-rose-50 text-rose-700 border border-rose-200",
    label: "Low confidence",
  },
} as const satisfies Record<AnswerConfidence, { badgeClass: string; label: string }>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Derives dot and text colors for a confidence percentage.
 *
 * @param pct - Integer confidence percentage (0–100).
 * @returns An object with `dotColor` and `textColor` hex strings.
 */
function resolveConfidenceColors(pct: number): {
  dotColor: string;
  textColor: string;
} {
  if (pct >= CONFIDENCE_HIGH_THRESHOLD) {
    return { dotColor: COLOR_EMERALD_DOT, textColor: COLOR_EMERALD_TEXT };
  }
  if (pct >= CONFIDENCE_MEDIUM_THRESHOLD) {
    return { dotColor: COLOR_AMBER_DOT, textColor: COLOR_AMBER_TEXT };
  }
  return { dotColor: COLOR_ROSE_DOT, textColor: COLOR_ROSE_TEXT };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Colored dot paired with a bold percentage label.
 *
 * @param pct - Integer confidence percentage (0–100).
 */
function ConfidencePip({ pct }: { readonly pct: number }): JSX.Element {
  const { dotColor, textColor } = resolveConfidenceColors(pct);
  return (
    <div className="flex items-center gap-2">
      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
      <span className="text-sm font-bold" style={{ color: textColor }}>
        {pct}%
      </span>
    </div>
  );
}

/**
 * Pill badge for a ReviewStatus value.
 *
 * @param status - The review status of the record.
 */
function StatusBadge({ status }: { readonly status: ReviewStatus }): JSX.Element {
  if (status === "REVIEWED") {
    return (
      <span className="px-3 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-md border border-emerald-100">
        Reviewed
      </span>
    );
  }
  return (
    <span className="px-3 py-1 bg-amber-50 text-amber-700 text-xs font-bold rounded-md border border-amber-100">
      Needs Review
    </span>
  );
}

/**
 * Small pill showing the confidence tier of an AI-recommended answer.
 *
 * @param confidence - The confidence tier for this answer.
 */
function AnswerConfidenceBadge({
  confidence,
}: {
  readonly confidence: AnswerConfidence;
}): JSX.Element {
  const { badgeClass, label } = ANSWER_CONFIDENCE_STYLE[confidence];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold flex-shrink-0 ${badgeClass}`}>
      {label}
    </span>
  );
}

/**
 * Card for a single unresolved form field with the AI answer and reasoning.
 *
 * @param field - The unresolved field data to display.
 */
function UnresolvedFieldCard({ field }: { readonly field: UnresolvedField }): JSX.Element {
  return (
    <div className="bg-white rounded-xl border border-outline-variant p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant leading-snug">
          {field.fieldName}
        </p>
        <AnswerConfidenceBadge confidence={field.answerConfidence} />
      </div>
      <p className="text-sm font-semibold text-on-surface leading-relaxed">{field.aiAnswer}</p>
      <p className="text-xs text-on-surface-variant leading-relaxed italic">{field.reasoning}</p>
    </div>
  );
}

/**
 * Right panel listing all AI-recommended answers for a record's unresolved fields.
 *
 * @param fields - The unresolved fields array from the review record.
 */
function AiRecommendedAnswers({
  fields,
}: {
  readonly fields: readonly UnresolvedField[];
}): JSX.Element {
  if (fields.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <span className="material-symbols-outlined text-4xl text-emerald-500">check_circle</span>
        <p className="text-sm font-semibold text-on-surface">No unresolved fields</p>
        <p className="text-xs text-on-surface-variant max-w-[20ch]">
          All fields were completed automatically with high confidence.
        </p>
      </div>
    );
  }

  const fieldCountLabel = fields.length === 1 ? "1 field" : `${fields.length} fields`;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant flex items-center gap-2">
        <span className="material-symbols-outlined text-sm">auto_fix_high</span>
        AI Recommended Answers
        <span
          className="ml-auto text-xs font-semibold normal-case tracking-normal px-2 py-0.5 rounded-full"
          style={{
            backgroundColor: `${COLOR_PRIMARY}1A`,
            color: COLOR_PRIMARY,
          }}
        >
          {fieldCountLabel}
        </span>
      </h4>
      <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
        {fields.map((field) => (
          <UnresolvedFieldCard key={field.fieldName} field={field} />
        ))}
      </div>
    </div>
  );
}

/**
 * Left panel showing the agent's diagnostic explanation and resource links.
 *
 * @param diagnostic - The agent's explanation of why automation was halted.
 * @param jobPostingUrl - URL to the original job posting.
 * @param resumeFileName - File name of the tailored resume PDF.
 */
function AgentDiagnosticsPanel({
  diagnostic,
  jobPostingUrl,
  resumeFileName,
}: {
  readonly diagnostic: string;
  readonly jobPostingUrl: string;
  readonly resumeFileName: string;
}): JSX.Element {
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant flex items-center gap-2">
        <span className="material-symbols-outlined text-sm">analytics</span>
        Why Flagged
      </h4>
      <div className="bg-surface-container-low border-l-4 border-indigo-500 p-5 rounded-r-xl">
        <p className="text-sm italic text-on-surface-variant leading-relaxed">"{diagnostic}"</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <a
          href={jobPostingUrl}
          className="flex items-center gap-3 p-3 bg-surface-container-high rounded-xl hover:bg-surface-container transition-all group"
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant group-hover:text-primary">
            link
          </span>
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-bold text-on-surface-variant">Resources</span>
            <span className="text-sm font-semibold text-on-surface truncate">Job Posting Link</span>
          </div>
        </a>
        <a
          href="#"
          className="flex items-center gap-3 p-3 bg-surface-container-high rounded-xl hover:bg-surface-container transition-all group"
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant group-hover:text-primary">
            description
          </span>
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-bold text-on-surface-variant">Resume</span>
            <span className="text-sm font-semibold text-on-surface truncate">{resumeFileName}</span>
          </div>
        </a>
      </div>
    </div>
  );
}

/**
 * Expanded detail panel rendered as a second `<tr>` below the selected row.
 *
 * @param record - The review record being expanded.
 * @param onDismiss - Called when the user clicks "Dismiss".
 * @param onMarkComplete - Called when the user clicks "Mark Complete".
 */
function ExpandedDetailPanel({
  record,
  onDismiss,
  onMarkComplete,
}: {
  readonly record: ReviewRecord;
  readonly onDismiss: () => void;
  readonly onMarkComplete: () => void;
}): JSX.Element {
  return (
    <tr>
      <td className="p-0" colSpan={TABLE_COLUMNS.length}>
        <div className="bg-surface-container-low/30 px-8 pb-10">
          <div className="bg-white p-8 rounded-2xl shadow-sm space-y-6">
            <div className="grid grid-cols-2 gap-8">
              <AgentDiagnosticsPanel
                diagnostic={record.agentDiagnostic}
                jobPostingUrl={record.jobPostingUrl}
                resumeFileName={record.resumeFileName}
              />
              <AiRecommendedAnswers fields={record.unresolvedFields} />
            </div>
            <div className="pt-6 border-t border-surface-container flex justify-end gap-3">
              <button
                type="button"
                className="px-6 py-2.5 border font-semibold rounded-full hover:bg-surface-container transition-all"
                style={{ borderColor: COLOR_OUTLINE_VARIANT }}
                onClick={onDismiss}
              >
                Dismiss
              </button>
              <button
                type="button"
                className="px-6 py-2.5 text-white font-bold rounded-full shadow-lg flex items-center gap-2 transition-all hover:opacity-90"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onMarkComplete}
              >
                <span className="material-symbols-outlined text-sm">check_circle</span>
                Mark Complete
              </button>
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

/**
 * A single table row plus its optional expanded detail panel.
 *
 * @param record - The review record to render.
 * @param isExpanded - Whether the detail panel is currently visible.
 * @param onToggle - Toggles expanded state when the row is clicked.
 * @param onDismiss - Called when the user dismisses this application.
 * @param onMarkComplete - Called when the user marks this application complete.
 */
function ReviewTableRow({
  record,
  isExpanded,
  onToggle,
  onDismiss,
  onMarkComplete,
}: {
  readonly record: ReviewRecord;
  readonly isExpanded: boolean;
  readonly onToggle: () => void;
  readonly onDismiss: () => void;
  readonly onMarkComplete: () => void;
}): JSX.Element {
  const isReviewed = record.status === "REVIEWED";
  const rowBgClass = isExpanded ? "bg-surface-container-low/30" : "hover:bg-surface-container-low";

  return (
    <>
      <tr className={`cursor-pointer transition-colors ${rowBgClass}`} onClick={onToggle}>
        <td className="px-8 py-5">
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs ${record.avatarBgClass} ${record.avatarTextClass}`}
            >
              {record.companyInitial}
            </div>
            <span className="font-semibold text-on-surface">{record.companyName}</span>
          </div>
        </td>
        <td className="px-8 py-5 text-on-surface-variant font-medium">{record.position}</td>
        <td className="px-8 py-5">
          <StatusBadge status={record.status} />
        </td>
        <td className="px-8 py-5">
          <ConfidencePip pct={record.confidencePct} />
        </td>
        <td className="px-8 py-5 text-on-surface-variant text-sm font-medium">
          {record.appliedDate}
        </td>
        <td className="px-8 py-5 text-right">
          {isExpanded ? (
            <span className="material-symbols-outlined text-primary">keyboard_arrow_up</span>
          ) : (
            <span
              className={`text-sm font-bold hover:underline ${
                isReviewed ? "text-on-surface-variant" : "text-primary"
              }`}
            >
              {isReviewed ? "View" : "Review"}
            </span>
          )}
        </td>
      </tr>
      {isExpanded && (
        <ExpandedDetailPanel
          record={record}
          onDismiss={onDismiss}
          onMarkComplete={onMarkComplete}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

/**
 * Human Review page — root component for the `/human-review` route.
 *
 * @returns The full scrollable content area for the Human Review page.
 */
export function HumanReviewPage(): JSX.Element {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");

  function handleSearchChange(event: React.ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.target.value);
  }

  function handleRowToggle(id: number): void {
    setExpandedRow((prev) => (prev === id ? null : id));
  }

  function handleDismiss(id: number): void {
    // TODO: call DELETE /api/human-review/{id}/dismiss
    setExpandedRow(null);
    console.info("Dismissed review record", id);
  }

  function handleMarkComplete(id: number): void {
    // TODO: call POST /api/human-review/{id}/complete
    setExpandedRow(null);
    console.info("Marked review record complete", id);
  }

  const visibleRecords = searchQuery.trim()
    ? REVIEW_RECORDS.filter(
        (r) =>
          r.companyName.toLowerCase().includes(searchQuery.toLowerCase()) ||
          r.position.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : REVIEW_RECORDS;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Page header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-1">
          <h2 className="text-3xl font-extrabold tracking-tight text-on-surface">
            Human Review Queue
          </h2>
          <p className="font-medium text-on-surface-variant">
            Verify and confirm automated applications requiring manual input.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="px-5 py-2.5 border font-semibold rounded-full hover:bg-surface-container transition-all flex items-center gap-2"
            style={{ borderColor: COLOR_OUTLINE_VARIANT }}
          >
            <span className="material-symbols-outlined text-[20px]">file_download</span>
            Export CSV
          </button>
          <button
            type="button"
            className="px-6 py-2.5 text-white font-bold rounded-full shadow-lg flex items-center gap-2 active:scale-95 transition-all"
            style={{
              background: `linear-gradient(to top right, ${COLOR_PRIMARY}, ${COLOR_PRIMARY_CONTAINER})`,
              boxShadow: `0 4px 14px ${COLOR_PRIMARY}40`,
            }}
          >
            <span className="material-symbols-outlined text-[20px]">bolt</span>
            Review Next
          </button>
        </div>
      </div>

      {/* Search + filter row */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant">
            search
          </span>
          <input
            className="w-full pl-12 pr-4 py-3 bg-surface-container-high rounded-xl border-none focus:outline-none font-medium placeholder:text-on-surface-variant transition-all"
            placeholder="Search by company or position..."
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </div>
        <button
          type="button"
          className="px-6 py-3 bg-surface-container-high text-on-surface font-semibold rounded-xl hover:bg-surface-container transition-all flex items-center gap-2"
        >
          <span className="material-symbols-outlined">filter_list</span>
          Filter
        </button>
      </div>

      {/* Data table */}
      <div className="bg-white rounded-[1.5rem] shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-low/50">
              {TABLE_COLUMNS.map((col) => (
                <th
                  key={col}
                  className={`px-8 py-5 text-[11px] font-bold uppercase tracking-widest text-on-surface-variant ${
                    col === "Actions" ? "text-right" : ""
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-container">
            {visibleRecords.map((record) => (
              <ReviewTableRow
                key={record.id}
                record={record}
                isExpanded={expandedRow === record.id}
                onToggle={() => handleRowToggle(record.id)}
                onDismiss={() => handleDismiss(record.id)}
                onMarkComplete={() => handleMarkComplete(record.id)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-2">
        <span className="text-sm font-medium text-on-surface-variant">
          Showing 1–{visibleRecords.length} of 12 applications
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="w-10 h-10 flex items-center justify-center border rounded-xl text-on-surface-variant hover:bg-surface-container transition-all"
            style={{ borderColor: COLOR_OUTLINE_VARIANT }}
          >
            <span className="material-symbols-outlined">chevron_left</span>
          </button>
          <button
            type="button"
            className="w-10 h-10 flex items-center justify-center text-white font-bold rounded-xl shadow-md"
            style={{ backgroundColor: COLOR_PRIMARY }}
          >
            1
          </button>
          <button
            type="button"
            className="w-10 h-10 flex items-center justify-center border text-on-surface font-semibold rounded-xl hover:bg-surface-container transition-all"
            style={{ borderColor: COLOR_OUTLINE_VARIANT }}
          >
            2
          </button>
          <button
            type="button"
            className="w-10 h-10 flex items-center justify-center border rounded-xl text-on-surface-variant hover:bg-surface-container transition-all"
            style={{ borderColor: COLOR_OUTLINE_VARIANT }}
          >
            <span className="material-symbols-outlined">chevron_right</span>
          </button>
        </div>
      </div>
    </div>
  );
}
