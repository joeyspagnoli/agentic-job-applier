/**
 * @packageDocumentation
 *
 * Structured guided editor body for the resume. Renders read-only personal +
 * education sections, layout knobs, and the experience/projects/skills
 * listing sub-sections.
 */

import type { JSX } from "react";
import type { ResumeContentDto } from "@/lib/api/types";
import { COLOR_ON_SURFACE_VARIANT, COLOR_PRIMARY } from "@/lib/design-tokens";
import { getErrorMessage } from "@/lib/settings/transforms";
import { useResumeDraftHandlers } from "@/lib/settings/useResumeDraftHandlers";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import {
  ResumeExperienceSection,
  ResumeProjectsSection,
  ResumeSkillsSection,
} from "./ResumeListingSections";

/** Props for the structured resume editor body. */
export interface ResumeGuidedViewProps {
  /** Current resume draft. */
  readonly resumeDraft: ResumeContentDto;
  /** Callback that fully replaces the draft (functional updates accepted). */
  readonly onDraftChange: (
    next: ResumeContentDto | ((current: ResumeContentDto) => ResumeContentDto),
  ) => void;
  /** True while the structured save mutation is pending. */
  readonly isPending: boolean;
  /** True when the draft has unsaved changes. */
  readonly isDirty: boolean;
  /** True when the structured save mutation errored. */
  readonly isError: boolean;
  /** Optional error from the structured save mutation. */
  readonly errorMessage: unknown;
  /** Persist the structured draft. */
  readonly onSave: () => void;
}

/**
 * Render the structured resume editor body.
 *
 * @param props - View props.
 * @returns Guided resume editor markup.
 */
export function ResumeGuidedView({
  resumeDraft,
  onDraftChange,
  isPending,
  isDirty,
  isError,
  errorMessage,
  onSave,
}: ResumeGuidedViewProps): JSX.Element {
  const handlers = useResumeDraftHandlers(onDraftChange);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4">
        <h4 className="text-sm font-bold uppercase tracking-wide">Locked Sections (Read-Only)</h4>
        <p className="mt-2 text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Personal and education sections are locked by resume policy.
        </p>
        <p className="mt-3 text-sm">
          <strong>{resumeDraft.personal.name}</strong> • {resumeDraft.personal.email} •{" "}
          {resumeDraft.personal.phone}
        </p>
        {resumeDraft.education.entries.map((entry) => (
          <div key={entry.id} className="mt-2 text-sm">
            <p>
              <strong>{entry.institution}</strong> ({entry.date_range})
            </p>
            <p>{entry.degree}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
        <h4 className="text-sm font-bold uppercase tracking-wide">Layout Knobs</h4>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          {Object.entries(resumeDraft.layout).map(([fieldName, fieldValue]) => (
            <label key={fieldName} className="text-xs font-semibold">
              {fieldName}
              <input
                className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
                type="number"
                step="0.01"
                value={fieldValue}
                onChange={(event) =>
                  handlers.updateLayoutField(
                    fieldName as keyof ResumeContentDto["layout"],
                    event.target.value,
                  )
                }
              />
            </label>
          ))}
        </div>
      </div>

      <ResumeExperienceSection
        listings={resumeDraft.experience.listings}
        onFieldUpdate={handlers.updateExperienceField}
        onBulletsUpdate={handlers.updateExperienceBullets}
        onAdd={handlers.addExperienceListing}
        onRemove={handlers.removeExperienceListing}
      />

      <ResumeProjectsSection
        listings={resumeDraft.projects.listings}
        onFieldUpdate={handlers.updateProjectField}
        onBulletsUpdate={handlers.updateProjectBullets}
        onAdd={handlers.addProjectListing}
        onRemove={handlers.removeProjectListing}
      />

      <ResumeSkillsSection
        listings={resumeDraft.skills_achievements.listings}
        onFieldUpdate={handlers.updateSkillField}
        onAdd={handlers.addSkillListing}
        onRemove={handlers.removeSkillListing}
      />

      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isPending || !isDirty}
        >
          {isPending ? "Saving..." : "Save Resume"}
        </button>
      </div>
      {isError && (
        <InlineErrorText message={`Resume save failed: ${getErrorMessage(errorMessage)}`} />
      )}
    </div>
  );
}
