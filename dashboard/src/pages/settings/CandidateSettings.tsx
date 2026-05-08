/**
 * @packageDocumentation
 *
 * Composer for the "Profile & Resume" top-level settings tab. Renders the
 * profile and resume sections side-by-side and forwards their dirty/error
 * notifications to the parent shell.
 */

import type { JSX } from "react";
import { ProfileSettings } from "./ProfileSettings";
import { ResumeSettings } from "./ResumeSettings";

/** Props for the candidate settings composer. */
export interface CandidateSettingsProps {
  /** Callback invoked whenever the profile section dirty flag changes. */
  readonly onProfileDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked whenever the profile section error state changes. */
  readonly onProfileErrorChange: (hasError: boolean) => void;
  /** Callback invoked whenever the resume section dirty flag changes. */
  readonly onResumeDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked whenever the resume section error state changes. */
  readonly onResumeErrorChange: (hasError: boolean) => void;
}

/**
 * Render the Profile & Resume tab.
 *
 * @param props - Composer props.
 * @returns Stacked profile + resume sections.
 */
export function CandidateSettings({
  onProfileDirtyChange,
  onProfileErrorChange,
  onResumeDirtyChange,
  onResumeErrorChange,
}: CandidateSettingsProps): JSX.Element {
  return (
    <>
      <ProfileSettings
        onDirtyChange={onProfileDirtyChange}
        onErrorChange={onProfileErrorChange}
      />
      <ResumeSettings
        onDirtyChange={onResumeDirtyChange}
        onErrorChange={onResumeErrorChange}
      />
    </>
  );
}
