/**
 * @packageDocumentation
 *
 * Sources YAML editor view inside the Filters & Sources tab. Receives the
 * draft YAML and saving state from the parent composer so the draft is
 * preserved across sub-tab switches.
 */

import type { JSX } from "react";
import {
  COLOR_ON_WARNING_CONTAINER,
  COLOR_OUTLINE,
  COLOR_PRIMARY,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { YamlEditor } from "@/components/settings/YamlEditor";

/** Props for the sources YAML editor view. */
export interface SourcesSettingsProps {
  /** Current sources YAML draft text. */
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
 * Render the companies/sources YAML editor view.
 *
 * @param props - Editor view props.
 * @returns Sources editor element.
 */
export function SourcesSettings({
  draft,
  isDirty,
  isLoading,
  isQueryError,
  isSaving,
  saveErrorMessage,
  onDraftChange,
  onSave,
}: SourcesSettingsProps): JSX.Element {
  return (
    <div className="space-y-4">
      <div
        className="rounded-xl border px-4 py-3 text-sm"
        style={{
          borderColor: COLOR_WARNING,
          color: COLOR_ON_WARNING_CONTAINER,
          backgroundColor: COLOR_WARNING_CONTAINER,
        }}
      >
        Danger Zone: aggressive LinkedIn/source settings may cause rate limiting or IP blocks.
      </div>
      <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
        Advanced: edit `companies.yaml` directly.
      </p>
      <YamlEditor modelPath="companies.yaml" value={draft} onChange={onDraftChange} />
      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isSaving || !isDirty}
        >
          {isSaving ? "Saving..." : "Save Sources"}
        </button>
      </div>
      {isLoading && (
        <p className="text-sm" style={{ color: COLOR_OUTLINE }}>
          Loading sources configuration...
        </p>
      )}
      {isQueryError && <InlineErrorText message="Failed to load sources configuration." />}
      {saveErrorMessage !== null && (
        <InlineErrorText message={`Save failed: ${saveErrorMessage}`} />
      )}
    </div>
  );
}
