/**
 * @packageDocumentation
 *
 * Resume editor section orchestrator. Routes between the guided / YAML / tex
 * / files sub-tabs and shows an unsupported-tier panel when the active
 * service tier does not permit resume editing.
 */

import type { JSX } from "react";
import { useState } from "react";
import { getResumeDownloadUrl } from "@/lib/api/client";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_ON_WARNING_CONTAINER,
  COLOR_OUTLINE,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { getErrorMessage } from "@/lib/settings/transforms";
import type { ResumeTab } from "@/lib/settings/types";
import { useResumeMutations } from "@/lib/settings/useResumeMutations";
import { TabButton } from "@/components/settings/TabButton";
import { ResumeFilesView, ResumeTexView, ResumeYamlView } from "./ResumeFileActions";
import { ResumeGuidedView } from "./ResumeGuidedView";

/** Props for the resume settings section. */
export interface ResumeSettingsProps {
  /** Callback invoked whenever the dirty flag changes. */
  readonly onDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked whenever the section error state changes. */
  readonly onErrorChange: (hasError: boolean) => void;
}

/**
 * Render the resume editor section.
 *
 * @param props - Section props.
 * @returns Resume editor section element (or unsupported-tier panel).
 */
export function ResumeSettings({
  onDirtyChange,
  onErrorChange,
}: ResumeSettingsProps): JSX.Element {
  const [resumeTab, setResumeTab] = useState<ResumeTab>("guided");
  const state = useResumeMutations(onDirtyChange, onErrorChange);

  if (!state.canOpenResumeEditor) {
    return (
      <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-4">
        <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Resume Editor
        </h3>
        <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Resume editor is available only for LaTeX or Full tiers.
        </p>
        <div
          className="rounded-xl border px-4 py-3 text-sm"
          style={{
            borderColor: COLOR_WARNING,
            color: COLOR_ON_WARNING_CONTAINER,
            backgroundColor: COLOR_WARNING_CONTAINER,
          }}
        >
          Select LaTeX or Full in <strong>General Settings → Service Tier</strong> to enable resume
          tailoring and review workflows.
        </div>
      </section>
    );
  }

  const yamlSaveErrorMessage = state.resumeYamlMutation.isError
    ? getErrorMessage(state.resumeYamlMutation.error)
    : null;
  const texErrorMessage = state.resumeTexMutation.isError
    ? getErrorMessage(state.resumeTexMutation.error)
    : null;
  const uploadErrorMessage = state.resumeUploadMutation.isError
    ? getErrorMessage(state.resumeUploadMutation.error)
    : null;

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Resume Editor
          </h3>
          <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Resume editing is enabled for LaTeX and Full tiers.
          </p>
          <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
            {state.resumeCountsText}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TabButton
            active={resumeTab === "guided"}
            label="Guided"
            onClick={() => setResumeTab("guided")}
          />
          <TabButton
            active={resumeTab === "yaml"}
            label="Advanced YAML"
            onClick={() => setResumeTab("yaml")}
          />
          <TabButton
            active={resumeTab === "tex"}
            label="Upload TeX"
            onClick={() => setResumeTab("tex")}
          />
          <TabButton
            active={resumeTab === "files"}
            label="File Actions"
            onClick={() => setResumeTab("files")}
          />
        </div>
      </div>

      {resumeTab === "guided" && state.resumeDraft !== null && (
        <ResumeGuidedView
          resumeDraft={state.resumeDraft}
          onDraftChange={state.handleResumeDraftChange}
          isPending={state.resumeStructuredMutation.isPending}
          isDirty={state.isResumeDirty}
          isError={state.resumeStructuredMutation.isError}
          errorMessage={state.resumeStructuredMutation.error}
          onSave={state.handleResumeGuidedSave}
        />
      )}

      {resumeTab === "yaml" && (
        <ResumeYamlView
          draft={state.resumeYamlDraft}
          isDirty={state.isResumeDirty}
          isSaving={state.resumeYamlMutation.isPending}
          saveErrorMessage={yamlSaveErrorMessage}
          onDraftChange={state.handleResumeYamlDraftChange}
          onSave={state.handleResumeYamlSave}
        />
      )}

      {resumeTab === "tex" && (
        <ResumeTexView
          isConverting={state.resumeTexMutation.isPending}
          migrationSummary={state.lastMigrationSummary}
          errorMessage={texErrorMessage}
          onFileSelected={state.handleResumeTexUpload}
        />
      )}

      {resumeTab === "files" && (
        <ResumeFilesView
          metadataSubtitle={state.fileSubtitle}
          downloadUrl={getResumeDownloadUrl()}
          isUploading={state.resumeUploadMutation.isPending}
          errorMessage={uploadErrorMessage}
          onFileSelected={state.handleResumeYamlUpload}
        />
      )}
    </section>
  );
}
