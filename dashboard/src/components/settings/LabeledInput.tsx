/**
 * @packageDocumentation
 *
 * Single-line labeled text input used throughout the guided settings forms.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";

/** Props for labeled single-line input. */
export interface LabeledInputProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one labeled text input.
 *
 * @param props - Labeled input props.
 * @returns One input field block.
 */
export function LabeledInput({ label, value, onChange }: LabeledInputProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </label>
  );
}
