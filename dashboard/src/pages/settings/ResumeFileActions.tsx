/**
 * @packageDocumentation
 *
 * Three small file-action views for the Resume Editor: raw YAML save panel,
 * TeX upload + migration panel, and download/replace files panel.
 */

import type { ChangeEvent, JSX } from "react";
import { useRef } from "react";
import { RESUME_EDITOR_MODEL_URI } from "@/lib/monaco/yaml-config";
import {
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_PRIMARY,
  COLOR_SUCCESS,
} from "@/lib/design-tokens";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { SettingsFileCard } from "@/components/settings/SettingsFileCard";
import { YamlEditor } from "@/components/settings/YamlEditor";

/** Props for the raw resume YAML editor view. */
export interface ResumeYamlViewProps {
  /** Current YAML draft text. */
  readonly draft: string;
  /** Whether the draft has unsaved changes. */
  readonly isDirty: boolean;
  /** True while the save mutation is in flight. */
  readonly isSaving: boolean;
  /** Optional save error message. */
  readonly saveErrorMessage: string | null;
  /** Handler for editor draft changes. */
  readonly onDraftChange: (next: string) => void;
  /** Handler invoked when the user clicks the Save button. */
  readonly onSave: () => void;
}

/**
 * Render the raw resume YAML editor view.
 *
 * @param props - View props.
 * @returns Raw resume editor element.
 */
export function ResumeYamlView({
  draft,
  isDirty,
  isSaving,
  saveErrorMessage,
  onDraftChange,
  onSave,
}: ResumeYamlViewProps): JSX.Element {
  return (
    <div className="space-y-4">
      <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
        Advanced: edit raw resume YAML. Changes here override guided edits.
      </p>
      <YamlEditor modelPath={RESUME_EDITOR_MODEL_URI} value={draft} onChange={onDraftChange} />
      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={onSave}
          disabled={isSaving || !isDirty}
        >
          {isSaving ? "Saving..." : "Save YAML"}
        </button>
      </div>
      {saveErrorMessage !== null && (
        <InlineErrorText message={`YAML save failed: ${saveErrorMessage}`} />
      )}
    </div>
  );
}

/** Props for the TeX upload view. */
export interface ResumeTexViewProps {
  /** True while the TeX conversion mutation is in flight. */
  readonly isConverting: boolean;
  /** Last successful migration summary, or `null`. */
  readonly migrationSummary: string | null;
  /** Optional conversion error message. */
  readonly errorMessage: string | null;
  /** Handler invoked when the user picks a TeX file. */
  readonly onFileSelected: (event: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Render the TeX upload view.
 *
 * @param props - View props.
 * @returns TeX upload element.
 */
export function ResumeTexView({
  isConverting,
  migrationSummary,
  errorMessage,
  onFileSelected,
}: ResumeTexViewProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="space-y-4">
      <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        Upload a LaTeX resume source (`.tex`) and convert it into canonical YAML automatically.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".tex,text/plain"
        className="hidden"
        onChange={onFileSelected}
      />
      <button
        className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
        onClick={() => inputRef.current?.click()}
        disabled={isConverting}
      >
        {isConverting ? "Converting..." : "Upload TeX and Convert"}
      </button>
      {migrationSummary !== null && (
        <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
          Latest migration: {migrationSummary}
        </p>
      )}
      {errorMessage !== null && (
        <InlineErrorText message={`TeX conversion failed: ${errorMessage}`} />
      )}
    </div>
  );
}

/** Props for the resume files actions view. */
export interface ResumeFilesViewProps {
  /** Subtitle text for the file metadata card. */
  readonly metadataSubtitle: string;
  /** URL to download the canonical resume YAML. */
  readonly downloadUrl: string;
  /** True while the YAML upload mutation is in flight. */
  readonly isUploading: boolean;
  /** Optional upload error message. */
  readonly errorMessage: string | null;
  /** Handler invoked when the user picks a YAML file. */
  readonly onFileSelected: (event: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Render the resume file actions view.
 *
 * @param props - View props.
 * @returns Resume files action element.
 */
export function ResumeFilesView({
  metadataSubtitle,
  downloadUrl,
  isUploading,
  errorMessage,
  onFileSelected,
}: ResumeFilesViewProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="space-y-4">
      <SettingsFileCard
        title="Resume YAML"
        subtitle={metadataSubtitle}
        downloadUrl={downloadUrl}
      />
      <input
        ref={inputRef}
        type="file"
        accept=".yaml,.yml,text/yaml,application/x-yaml"
        className="hidden"
        onChange={onFileSelected}
      />
      <button
        className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
      >
        {isUploading ? "Uploading..." : "Replace Resume YAML"}
      </button>
      {errorMessage !== null && <InlineErrorText message={`Upload failed: ${errorMessage}`} />}
    </div>
  );
}
