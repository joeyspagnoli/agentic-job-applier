/**
 * @packageDocumentation
 *
 * Compact metadata + download card used for settings file actions.
 */

import type { JSX } from "react";
import { COLOR_OUTLINE, COLOR_PRIMARY } from "@/lib/design-tokens";

/** Props for compact file metadata cards. */
export interface SettingsFileCardProps {
  /** File card title. */
  readonly title: string;
  /** File metadata subtitle text. */
  readonly subtitle: string;
  /** Download URL for file action link. */
  readonly downloadUrl: string;
}

/**
 * Render one compact settings file metadata card.
 *
 * @param props - File card props.
 * @returns One file metadata card element.
 */
export function SettingsFileCard({
  title,
  subtitle,
  downloadUrl,
}: SettingsFileCardProps): JSX.Element {
  return (
    <div className="flex items-center justify-between rounded-xl border border-outline-variant bg-surface-container-low px-4 py-3">
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
          {subtitle}
        </p>
      </div>
      <a
        className="text-sm font-semibold hover:underline"
        href={downloadUrl}
        target="_blank"
        rel="noreferrer"
        style={{ color: COLOR_PRIMARY }}
      >
        Download
      </a>
    </div>
  );
}
