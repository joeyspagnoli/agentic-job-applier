/**
 * @packageDocumentation
 *
 * Education sub-section of the guided profile editor. Renders the per-entry
 * inputs and emits add/remove/update callbacks back to the parent.
 */

import type { JSX } from "react";
import type { CandidateEducationEntryDto } from "@/lib/api/types";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";
import { DEGREE_LEVEL_OPTIONS, MONTH_OPTIONS } from "@/lib/settings/constants";
import { listToLines } from "@/lib/settings/transforms";
import { LabeledInput } from "@/components/settings/LabeledInput";
import { LabeledSelect } from "@/components/settings/LabeledSelect";
import { LabeledTextarea } from "@/components/settings/LabeledTextarea";

/** Props for the education editor sub-section. */
export interface ProfileEducationSectionProps {
  /** Free-form summary line shown above the entries. */
  readonly educationSummary: string;
  /** Mutable education entries to render. */
  readonly entries: readonly CandidateEducationEntryDto[];
  /** Update the free-form summary line. */
  readonly onSummaryChange: (value: string) => void;
  /** Update one field on the education entry at `index`. */
  readonly onEntryFieldUpdate: (
    index: number,
    fieldName: keyof CandidateEducationEntryDto,
    value: string | boolean,
  ) => void;
  /** Replace the highlights list for the entry at `index`. */
  readonly onEntryHighlightsUpdate: (index: number, value: string) => void;
  /** Append a new empty entry. */
  readonly onEntryAdd: () => void;
  /** Remove the entry at `index`. */
  readonly onEntryRemove: (index: number) => void;
}

/**
 * Render the education editor sub-section.
 *
 * @param props - Sub-section props.
 * @returns Education sub-section markup.
 */
export function ProfileEducationSection({
  educationSummary,
  entries,
  onSummaryChange,
  onEntryFieldUpdate,
  onEntryHighlightsUpdate,
  onEntryAdd,
  onEntryRemove,
}: ProfileEducationSectionProps): JSX.Element {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Education
        </h5>
        <button
          className="text-sm font-semibold"
          style={{ color: COLOR_PRIMARY }}
          onClick={onEntryAdd}
        >
          + Add Education
        </button>
      </div>
      <LabeledInput
        label="Education Summary"
        value={educationSummary}
        onChange={onSummaryChange}
      />
      {entries.map((entry, entryIndex) => (
        <div
          key={entry.id}
          className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <LabeledInput
              label="School"
              value={entry.school}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "school", value)}
            />
            <LabeledSelect
              label="Degree Level"
              value={entry.degree_level}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "degree_level", value)}
              options={DEGREE_LEVEL_OPTIONS}
            />
            <LabeledInput
              label="Degree Name"
              value={entry.degree_name}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "degree_name", value)}
            />
            <LabeledInput
              label="Field of Study"
              value={entry.field_of_study}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "field_of_study", value)}
            />
            <LabeledInput
              label="Location"
              value={entry.location}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "location", value)}
            />
            <LabeledInput
              label="GPA (optional)"
              value={entry.gpa}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "gpa", value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
            <LabeledSelect
              label="Start Month"
              value={entry.start_month}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "start_month", value)}
              options={MONTH_OPTIONS}
            />
            <LabeledInput
              label="Start Year"
              value={entry.start_year}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "start_year", value)}
            />
            <LabeledSelect
              label="End Month"
              value={entry.end_month}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "end_month", value)}
              options={MONTH_OPTIONS}
            />
            <LabeledInput
              label="End Year"
              value={entry.end_year}
              onChange={(value) => onEntryFieldUpdate(entryIndex, "end_year", value)}
            />
            <label
              className="mt-6 text-xs font-semibold"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              <input
                type="checkbox"
                checked={entry.is_current}
                onChange={(event) =>
                  onEntryFieldUpdate(entryIndex, "is_current", event.target.checked)
                }
              />{" "}
              Currently enrolled
            </label>
          </div>
          <LabeledTextarea
            label="Highlights (one per line)"
            value={listToLines(entry.highlights)}
            onChange={(value) => onEntryHighlightsUpdate(entryIndex, value)}
            rows={3}
            helperText={`${entry.highlights.length} item(s)`}
          />
          <div className="flex justify-end">
            <button
              className="text-xs font-semibold"
              style={{ color: COLOR_ERROR }}
              onClick={() => onEntryRemove(entryIndex)}
            >
              Remove
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
