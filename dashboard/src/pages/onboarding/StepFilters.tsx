/**
 * @packageDocumentation
 *
 * Step 4 of the onboarding wizard: hard filters that exclude jobs before
 * they reach the candidate.
 */

import type { JSX } from "react";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
} from "@/lib/design-tokens";
import type { FiltersDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** All available job type options. */
const JOB_TYPE_OPTIONS = ["Full-time", "Part-time", "Contract", "Internship"] as const;

/** Props for {@link StepFilters}. */
export interface StepFiltersProps {
  /** Current filters draft. */
  readonly draft: FiltersDraft;
  /** Replace the draft with `next`. */
  readonly onChange: (next: FiltersDraft) => void;
}

/**
 * Step 4: Hard filters for job search.
 *
 * @param props - {@link StepFiltersProps}
 * @returns Filters form fields.
 */
export function StepFilters({ draft, onChange }: StepFiltersProps): JSX.Element {
  /**
   * Toggle a job type in the selected list.
   *
   * @param jt - Job type to toggle.
   */
  function toggleJobType(jt: string): void {
    const next = draft.jobTypes.includes(jt)
      ? draft.jobTypes.filter((t) => t !== jt)
      : [...draft.jobTypes, jt];
    onChange({ ...draft, jobTypes: next });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Filters
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Set hard filters to automatically exclude irrelevant jobs.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Min Salary (USD)"
          value={draft.minSalary}
          onChange={(v) => {
            onChange({ ...draft, minSalary: v });
          }}
          placeholder="80000"
          type="number"
        />
        <Field
          label="Max Salary (USD)"
          value={draft.maxSalary}
          onChange={(v) => {
            onChange({ ...draft, maxSalary: v });
          }}
          placeholder="200000"
          type="number"
        />
      </div>

      <div>
        <span
          className="text-xs font-semibold mb-2 block"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
        >
          Job Types
        </span>
        <div className="flex flex-wrap gap-2">
          {JOB_TYPE_OPTIONS.map((jt) => (
            <button
              key={jt}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border"
              style={{
                backgroundColor: draft.jobTypes.includes(jt) ? COLOR_PRIMARY_FIXED : "transparent",
                color: draft.jobTypes.includes(jt) ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                borderColor: draft.jobTypes.includes(jt)
                  ? `${COLOR_PRIMARY}40`
                  : COLOR_OUTLINE_VARIANT,
              }}
              onClick={() => {
                toggleJobType(jt);
              }}
            >
              {jt}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={draft.requireRemote}
          onChange={(e) => {
            onChange({ ...draft, requireRemote: e.target.checked });
          }}
          className="w-4 h-4 rounded accent-primary"
        />
        <span className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
          Only show remote/hybrid positions
        </span>
      </label>

      <Field
        label="Exclude Title Patterns (one per line)"
        value={draft.excludeTitlePatterns}
        onChange={(v) => {
          onChange({ ...draft, excludeTitlePatterns: v });
        }}
        placeholder="intern&#10;junior&#10;director"
        multiline
      />
      <Field
        label="Exclude Companies (one per line)"
        value={draft.excludeCompanies}
        onChange={(v) => {
          onChange({ ...draft, excludeCompanies: v });
        }}
        placeholder="Acme Corp&#10;Initech"
        multiline
      />
    </div>
  );
}
