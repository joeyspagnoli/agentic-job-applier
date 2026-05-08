/**
 * @packageDocumentation
 *
 * Dismissible warning banner used by the onboarding wizard for watchlist-
 * resolution failures.
 *
 * @remarks
 * Pure presentation: the parent owns the message string and the dismiss
 * callback so the wizard can render multiple banners independently.
 */

import type { JSX } from "react";
import { COLOR_WARNING } from "@/lib/design-tokens";

/** Props for {@link WarningBanner}. */
export interface WarningBannerProps {
  /** The warning copy to render. */
  readonly message: string;
  /** Called when the user clicks the dismiss button. */
  readonly onDismiss: () => void;
  /**
   * Tailwind `mt-*` class to control vertical spacing relative to the
   * preceding banner. Defaults to `mt-4`; pass `"mt-2"` for a stacked
   * banner directly below another.
   */
  readonly marginTopClass?: string;
}

/**
 * Render a dismissible warning banner.
 *
 * @param props - {@link WarningBannerProps}
 * @returns The banner element.
 */
export function WarningBanner({
  message,
  onDismiss,
  marginTopClass = "mt-4",
}: WarningBannerProps): JSX.Element {
  return (
    <div
      className={`${marginTopClass} flex items-start gap-2 rounded-lg p-3 text-sm font-medium`}
      style={{ backgroundColor: `${COLOR_WARNING}18`, color: COLOR_WARNING }}
    >
      <span className="flex-1">{message}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 opacity-60 hover:opacity-100"
      >
        ✕
      </button>
    </div>
  );
}
