/**
 * @packageDocumentation
 *
 * Compact pill-style tab button used by the settings page section headers.
 */

import type { JSX } from "react";
import {
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";

/** Props for settings section tab buttons. */
export interface TabButtonProps {
  /** Whether the tab is currently active. */
  readonly active: boolean;
  /** Tab label text. */
  readonly label: string;
  /** Click handler for tab activation. */
  readonly onClick: () => void;
}

/**
 * Render one compact settings tab button.
 *
 * @param props - Tab button props.
 * @returns One tab button element.
 */
export function TabButton({ active, label, onClick }: TabButtonProps): JSX.Element {
  return (
    <button
      className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
        active ? "text-white" : "bg-white"
      }`}
      style={
        active
          ? { backgroundColor: COLOR_PRIMARY, borderColor: COLOR_PRIMARY }
          : { color: COLOR_ON_SURFACE_VARIANT, borderColor: COLOR_OUTLINE_VARIANT }
      }
      onClick={onClick}
    >
      {label}
    </button>
  );
}
