/**
 * @packageDocumentation
 *
 * Structured guided editor body for the candidate profile. Receives the draft
 * + a single replace callback from the parent and delegates field-level
 * mutations to a derived handler hook.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_PRIMARY } from "@/lib/design-tokens";
import { countListItems, getErrorMessage, listToLines } from "@/lib/settings/transforms";
import type { ProfileDraft } from "@/lib/settings/transforms";
import { useProfileDraftHandlers } from "@/lib/settings/useProfileDraftHandlers";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { LabeledTextarea } from "@/components/settings/LabeledTextarea";
import { ProfileContactSection } from "./ProfileContactSection";
import { ProfileEducationSection } from "./ProfileEducationSection";

/** Props for the structured profile editor body. */
export interface ProfileGuidedViewProps {
  /** Current draft state. */
  readonly profileDraft: ProfileDraft;
  /** Callback that fully replaces the draft (functional updates accepted). */
  readonly onDraftChange: (
    next: ProfileDraft | ((current: ProfileDraft) => ProfileDraft),
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
 * Render the structured profile editor body.
 *
 * @param props - View props.
 * @returns Guided profile editor markup.
 */
export function ProfileGuidedView({
  profileDraft,
  onDraftChange,
  isPending,
  isDirty,
  isError,
  errorMessage,
  onSave,
}: ProfileGuidedViewProps): JSX.Element {
  const handlers = useProfileDraftHandlers(onDraftChange);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
        <h4
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: COLOR_ON_SURFACE }}
        >
          Core Context
        </h4>
        <LabeledTextarea
          label="Summary"
          value={profileDraft.profile.summary}
          onChange={(value) => handlers.updateScalar("summary", value)}
          rows={4}
          helperText={`${profileDraft.profile.summary.trim().length} character(s)`}
        />

        <ProfileContactSection
          contact={profileDraft.profile.contact}
          workAuthorization={profileDraft.profile.work_authorization}
          countryOptions={handlers.countryOptions}
          onContactFieldChange={handlers.updateContactField}
          onContactCountryChange={handlers.updateContactCountry}
          onWorkAuthorizationFieldChange={handlers.updateWorkAuthorizationField}
          onCitizenshipCountryChange={handlers.updateCitizenshipCountry}
        />

        <ProfileEducationSection
          educationSummary={profileDraft.profile.education_summary}
          entries={profileDraft.profile.education_entries}
          onSummaryChange={(value) => handlers.updateScalar("education_summary", value)}
          onEntryFieldUpdate={handlers.updateEducationField}
          onEntryHighlightsUpdate={handlers.updateEducationHighlights}
          onEntryAdd={handlers.addEducationEntry}
          onEntryRemove={handlers.removeEducationEntry}
        />
      </div>

      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
        <h4
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: COLOR_ON_SURFACE }}
        >
          Role Targeting
        </h4>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledTextarea
            label="Target Roles (one per line)"
            value={listToLines(profileDraft.profile.target_roles)}
            onChange={(value) => handlers.updateList("target_roles", value)}
            helperText={`${countListItems(listToLines(profileDraft.profile.target_roles))} item(s)`}
          />
          <LabeledTextarea
            label="Strongest Areas (one per line)"
            value={listToLines(profileDraft.profile.strongest_areas)}
            onChange={(value) => handlers.updateList("strongest_areas", value)}
            helperText={`${countListItems(listToLines(profileDraft.profile.strongest_areas))} item(s)`}
          />
          <LabeledTextarea
            label="Experience Highlights (one per line)"
            value={listToLines(profileDraft.profile.experience_highlights)}
            onChange={(value) => handlers.updateList("experience_highlights", value)}
            helperText={`${countListItems(listToLines(profileDraft.profile.experience_highlights))} item(s)`}
          />
          <LabeledTextarea
            label="Search Terms (one per line)"
            value={listToLines(profileDraft.search_defaults.job_board_search_terms)}
            onChange={handlers.updateSearchTerms}
            helperText={`${countListItems(listToLines(profileDraft.search_defaults.job_board_search_terms))} item(s)`}
          />
        </div>
      </div>

      <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-4">
        <h4
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: COLOR_ON_SURFACE }}
        >
          Decision Rules
        </h4>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledTextarea
            label="Hard Filters (one per line)"
            value={listToLines(profileDraft.profile.hard_filters)}
            onChange={(value) => handlers.updateList("hard_filters", value)}
            helperText={`${countListItems(listToLines(profileDraft.profile.hard_filters))} item(s)`}
          />
          <LabeledTextarea
            label="Preferences (one per line)"
            value={listToLines(profileDraft.profile.preferences)}
            onChange={(value) => handlers.updateList("preferences", value)}
            helperText={`${countListItems(listToLines(profileDraft.profile.preferences))} item(s)`}
          />
        </div>
      </div>

      <LabeledTextarea
        label="Prompt Context Override (optional)"
        value={profileDraft.prompt_context ?? ""}
        onChange={handlers.updatePromptContext}
        rows={6}
        helperText="Additional context injected into AI prompts."
      />

      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isPending || !isDirty}
        >
          {isPending ? "Saving..." : "Save Profile"}
        </button>
      </div>
      {isError && (
        <InlineErrorText message={`Profile save failed: ${getErrorMessage(errorMessage)}`} />
      )}
    </div>
  );
}
