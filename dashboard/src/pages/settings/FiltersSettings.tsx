/**
 * @packageDocumentation
 *
 * Filters tab views for the Filters & Sources page. Renders both the guided
 * structured editor and the raw YAML editor; the parent composer toggles
 * between them via the active sub-tab prop.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_OUTLINE, COLOR_PRIMARY } from "@/lib/design-tokens";
import { JOB_TYPES } from "@/lib/settings/constants";
import { countListItems } from "@/lib/settings/transforms";
import type { FiltersGuidedDraft } from "@/lib/settings/types";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { LabeledInput } from "@/components/settings/LabeledInput";
import { LabeledTextarea } from "@/components/settings/LabeledTextarea";
import { YamlEditor } from "@/components/settings/YamlEditor";

/** Props for the guided filters editor view. */
export interface FiltersGuidedSettingsProps {
  /** Current guided draft state. */
  readonly draft: FiltersGuidedDraft;
  /** Whether the draft has unsaved changes. */
  readonly isDirty: boolean;
  /** True when the underlying query is still loading. */
  readonly isLoading: boolean;
  /** True when the underlying query failed. */
  readonly isQueryError: boolean;
  /** True while the save mutation is in flight. */
  readonly isSaving: boolean;
  /** Optional save error message to surface inline. */
  readonly saveErrorMessage: string | null;
  /** Handler for incremental draft updates. */
  readonly onDraftChange: (nextDraft: FiltersGuidedDraft) => void;
  /** Handler invoked when the user clicks the Save button. */
  readonly onSave: () => void;
}

/**
 * Render the structured filters editor.
 *
 * @param props - Editor view props.
 * @returns Guided filters editor element.
 */
export function FiltersGuidedSettings({
  draft,
  isDirty,
  isLoading,
  isQueryError,
  isSaving,
  saveErrorMessage,
  onDraftChange,
  onSave,
}: FiltersGuidedSettingsProps): JSX.Element {
  return (
    <div className="space-y-6">
      {/* Hard Filters */}
      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
        <h4
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: COLOR_ON_SURFACE }}
        >
          Hard Filters
        </h4>
        <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
          Jobs matching any hard filter are rejected before entering the database.
        </p>

        <div className="space-y-2">
          <p className="text-xs font-semibold" style={{ color: COLOR_OUTLINE }}>
            Exclude Job Types
          </p>
          <div className="flex flex-wrap gap-2">
            {JOB_TYPES.map((jobType) => {
              const isChecked = draft.hard_exclude_job_types.includes(jobType);
              return (
                <label
                  key={jobType}
                  className="flex items-center gap-1.5 text-xs cursor-pointer select-none"
                  style={{ color: COLOR_ON_SURFACE }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {
                      const next = isChecked
                        ? draft.hard_exclude_job_types.filter((t) => t !== jobType)
                        : [...draft.hard_exclude_job_types, jobType];
                      onDraftChange({ ...draft, hard_exclude_job_types: next });
                    }}
                  />
                  {jobType}
                </label>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledTextarea
            label={`Exclude Title Patterns (${countListItems(draft.hard_exclude_title_patterns)} patterns) — one regex per line`}
            value={draft.hard_exclude_title_patterns}
            rows={5}
            onChange={(value) => onDraftChange({ ...draft, hard_exclude_title_patterns: value })}
          />
          <LabeledTextarea
            label={`Require Title Patterns (${countListItems(draft.hard_require_title_patterns)} patterns) — one regex per line, leave empty to disable`}
            value={draft.hard_require_title_patterns}
            rows={5}
            onChange={(value) => onDraftChange({ ...draft, hard_require_title_patterns: value })}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledTextarea
            label={`Exclude Locations (${countListItems(draft.hard_exclude_locations)} entries) — one substring per line`}
            value={draft.hard_exclude_locations}
            rows={3}
            onChange={(value) => onDraftChange({ ...draft, hard_exclude_locations: value })}
          />
          <LabeledTextarea
            label={`Exclude Companies (${countListItems(draft.hard_exclude_companies)} entries) — one per line`}
            value={draft.hard_exclude_companies}
            rows={3}
            onChange={(value) => onDraftChange({ ...draft, hard_exclude_companies: value })}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <LabeledInput
            label="Max Days Old (0 = disabled)"
            value={draft.hard_max_days_old}
            onChange={(value) => onDraftChange({ ...draft, hard_max_days_old: value })}
          />
          <LabeledInput
            label="Min Salary USD (0 = disabled)"
            value={draft.hard_min_salary_usd}
            onChange={(value) => onDraftChange({ ...draft, hard_min_salary_usd: value })}
          />
          <LabeledInput
            label="Max Salary USD (0 = disabled)"
            value={draft.hard_max_salary_usd}
            onChange={(value) => onDraftChange({ ...draft, hard_max_salary_usd: value })}
          />
        </div>

        <label
          className="flex items-center gap-2 text-xs font-semibold cursor-pointer select-none"
          style={{ color: COLOR_OUTLINE }}
        >
          <input
            type="checkbox"
            checked={draft.hard_require_remote}
            onChange={(event) =>
              onDraftChange({ ...draft, hard_require_remote: event.target.checked })
            }
          />
          Require Remote — only keep jobs flagged as remote or hybrid
        </label>
      </div>

      {/* Soft Filters */}
      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
        <h4
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: COLOR_ON_SURFACE }}
        >
          Soft Filters
        </h4>
        <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
          Soft filters auto-categorize jobs without running the gate agent.
        </p>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledTextarea
            label={`Negative Keywords — auto-FILTER (${countListItems(draft.soft_negative_keywords)} entries) — one per line`}
            value={draft.soft_negative_keywords}
            rows={5}
            onChange={(value) => onDraftChange({ ...draft, soft_negative_keywords: value })}
          />
          <LabeledTextarea
            label={`Positive Keywords — auto-QUALIFY (${countListItems(draft.soft_positive_keywords)} entries) — all must match`}
            value={draft.soft_positive_keywords}
            rows={5}
            onChange={(value) => onDraftChange({ ...draft, soft_positive_keywords: value })}
          />
        </div>

        <LabeledInput
          label="Max Experience Years (0 = disabled) — auto-FILTER if description mentions more than this"
          value={draft.soft_max_experience_years}
          onChange={(value) => onDraftChange({ ...draft, soft_max_experience_years: value })}
        />
      </div>

      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isSaving || !isDirty}
        >
          {isSaving ? "Saving..." : "Save Filters"}
        </button>
      </div>
      {isLoading && (
        <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
          Loading filters configuration...
        </p>
      )}
      {isQueryError && <InlineErrorText message="Failed to load filters configuration." />}
      {saveErrorMessage !== null && (
        <InlineErrorText message={`Save failed: ${saveErrorMessage}`} />
      )}
    </div>
  );
}

/** Props for the raw filters YAML editor view. */
export interface FiltersYamlSettingsProps {
  /** Current YAML draft text. */
  readonly draft: string;
  /** Whether the draft has unsaved changes. */
  readonly isDirty: boolean;
  /** True when the underlying query is still loading. */
  readonly isLoading: boolean;
  /** True when the underlying query failed. */
  readonly isQueryError: boolean;
  /** True while the save mutation is in flight. */
  readonly isSaving: boolean;
  /** Optional save error message to surface inline. */
  readonly saveErrorMessage: string | null;
  /** Handler for editor draft changes. */
  readonly onDraftChange: (nextDraft: string) => void;
  /** Handler invoked when the user clicks the Save button. */
  readonly onSave: () => void;
}

/**
 * Render the raw filters YAML editor view.
 *
 * @param props - Editor view props.
 * @returns Raw filters editor element.
 */
export function FiltersYamlSettings({
  draft,
  isDirty,
  isLoading,
  isQueryError,
  isSaving,
  saveErrorMessage,
  onDraftChange,
  onSave,
}: FiltersYamlSettingsProps): JSX.Element {
  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
        Advanced: edit `filters.yaml` directly.
      </p>
      <YamlEditor modelPath="filters.yaml" value={draft} onChange={onDraftChange} />
      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isSaving || !isDirty}
        >
          {isSaving ? "Saving..." : "Save Filters"}
        </button>
      </div>
      {isLoading && (
        <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
          Loading filters configuration...
        </p>
      )}
      {isQueryError && <InlineErrorText message="Failed to load filters configuration." />}
      {saveErrorMessage !== null && (
        <InlineErrorText message={`Save failed: ${saveErrorMessage}`} />
      )}
    </div>
  );
}
