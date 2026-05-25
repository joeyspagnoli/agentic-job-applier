/**
 * @packageDocumentation
 *
 * Onboarding wizard step capturing the candidate's education history.
 *
 * @remarks
 * The apply finisher fills Greenhouse education questions (degree pursuing,
 * expected graduation, currently enrolled, school) from this list. Before
 * this step existed the wizard emitted an empty `education_entries: []` and
 * those fields landed in NEEDS_REVIEW. Each entry mirrors the multi-row
 * pattern from `StepApplyPrefs` so users can add as many degrees as they
 * have (BS + MS, etc.).
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
import { defaultEducationEntry } from "@/lib/onboarding/defaults";
import type { EducationEntry } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepEducation}. */
export interface StepEducationProps {
  /** Current education list. */
  readonly draft: readonly EducationEntry[];
  /** Replace the entire list with `next`. */
  readonly onChange: (next: EducationEntry[]) => void;
}

/**
 * Step 2: Education history.
 *
 * @param props - {@link StepEducationProps}
 * @returns Education list with per-row controls.
 */
export function StepEducation({ draft, onChange }: StepEducationProps): JSX.Element {
  /**
   * Append a fresh empty row to the end of the list.
   */
  function addEntry(): void {
    onChange([...draft, defaultEducationEntry(draft.length)]);
  }

  /**
   * Remove one row by index.
   *
   * @param index - Position to delete.
   */
  function removeEntry(index: number): void {
    onChange(draft.filter((_, i) => i !== index));
  }

  /**
   * Update one field on one row.
   *
   * @param index - Row position to mutate.
   * @param key - Field to set on that row.
   * @param value - New value for the field.
   */
  function setField<K extends keyof EducationEntry>(
    index: number,
    key: K,
    value: EducationEntry[K],
  ): void {
    onChange(
      draft.map((entry, i) => (i === index ? { ...entry, [key]: value } : entry)),
    );
  }

  /**
   * Update the minors list from a newline-separated textarea string.
   *
   * @param index - Row position whose minors list is being edited.
   * @param raw - Raw textarea contents (one minor per line).
   */
  function setMinors(index: number, raw: string): void {
    const minors = raw
      .split("\n")
      .map((minor) => minor.trim())
      .filter(Boolean);
    setField(index, "minors", minors);
  }

  const checkboxClasses = "h-4 w-4 rounded border accent-primary cursor-pointer";

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Education
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Add each degree you have completed or are currently pursuing. The
          apply agent uses these entries to answer questions about degree,
          major, and expected graduation date.
        </p>
      </div>

      {draft.length === 0 && (
        <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          No education entries yet. Click <span className="font-semibold">+ Add education</span>{" "}
          to capture your first degree.
        </p>
      )}

      {draft.map((entry, index) => (
        <div
          key={entry.id}
          className="rounded-2xl border p-4 space-y-3"
          style={{ borderColor: "#e2e2e2" }}
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Entry {index + 1}
            </h3>
            <button
              type="button"
              className="text-sm font-medium px-3 py-1.5 rounded-lg"
              style={{ color: "#b91c1c" }}
              onClick={() => {
                removeEntry(index);
              }}
            >
              Remove
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field
              label="School"
              value={entry.school}
              onChange={(v) => {
                setField(index, "school", v);
              }}
              placeholder="University of Florida"
              required
            />
            <Field
              label="Degree"
              value={entry.degree}
              onChange={(v) => {
                setField(index, "degree", v);
              }}
              placeholder="Bachelor of Science"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Major"
              value={entry.major}
              onChange={(v) => {
                setField(index, "major", v);
              }}
              placeholder="Computer Science"
            />
            <Field
              label="GPA (optional)"
              value={entry.gpa}
              onChange={(v) => {
                setField(index, "gpa", v);
              }}
              placeholder="3.8"
            />
          </div>

          <Field
            label="Minors (one per line, optional)"
            value={entry.minors.join("\n")}
            onChange={(v) => {
              setMinors(index, v);
            }}
            placeholder={"Statistics\nElectrical Engineering"}
            multiline
          />

          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Start date (YYYY-MM)"
              value={entry.startDate}
              onChange={(v) => {
                setField(index, "startDate", v);
              }}
              placeholder="2022-08"
            />
            <Field
              label={
                entry.currentlyEnrolled
                  ? "Expected graduation (YYYY-MM)"
                  : "End date (YYYY-MM)"
              }
              value={entry.endDate}
              onChange={(v) => {
                setField(index, "endDate", v);
              }}
              placeholder="2026-05"
            />
          </div>

          <label
            className="flex items-center gap-2 cursor-pointer text-sm"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            <input
              type="checkbox"
              className={checkboxClasses}
              checked={entry.currentlyEnrolled}
              onChange={(event) => {
                setField(index, "currentlyEnrolled", event.target.checked);
              }}
            />
            Still enrolled — return after the internship
          </label>
        </div>
      ))}

      <button
        type="button"
        className="text-sm font-semibold px-4 py-2 rounded-xl border transition-colors"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
        onClick={addEntry}
      >
        + Add education
      </button>
    </div>
  );
}
