/**
 * @packageDocumentation
 *
 * Composer for the "Profile & Resume" top-level settings tab. The
 * Resume Editor sub-section was removed in the post-#61 cleanup
 * because the structured editor relied on the pre-`.tex` YAML payload
 * the backend no longer emits. The resume itself is uploaded through
 * the onboarding wizard's Resume step.
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
