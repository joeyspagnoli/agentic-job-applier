/**
 * @packageDocumentation
 *
 * Composer for the "Profile & Resume" top-level settings tab.
 * Resume editing is handled through the `.tex` upload and contract
 * validator flow in the onboarding wizard, not via an inline editor.
 */

import type { JSX } from "react";
import { ProfileSettings } from "./ProfileSettings";

/** Props for the candidate settings composer. */
export interface CandidateSettingsProps {
  /** Callback invoked whenever the profile section dirty flag changes. */
  readonly onProfileDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked whenever the profile section error state changes. */
  readonly onProfileErrorChange: (hasError: boolean) => void;
}

/**
 * Render the Profile tab.
 *
 * @param props - Composer props.
 * @returns Profile section.
 */
export function CandidateSettings({
  onProfileDirtyChange,
  onProfileErrorChange,
}: CandidateSettingsProps): JSX.Element {
  return (
    <ProfileSettings
      onDirtyChange={onProfileDirtyChange}
      onErrorChange={onProfileErrorChange}
    />
  );
}
