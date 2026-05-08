/**
 * @packageDocumentation
 *
 * Labeled multi-line textarea used throughout the guided settings forms.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE_VARIANT, COLOR_OUTLINE } from "@/lib/design-tokens";

/** Props for labeled textarea input. */
export interface LabeledTextareaProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
  /** Optional row count override. */
  readonly rows?: number;
  /** Optional helper text shown below textarea. */
  readonly helperText?: string;
}

/**
 * Render one labeled textarea.
 *
 * @param props - Labeled textarea props.
 * @returns One textarea block.
 */
export function LabeledTextarea({
  label,
  value,
  onChange,
  rows = 5,
  helperText,
}: LabeledTextareaProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <textarea
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-2 text-sm"
        rows={rows}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {helperText !== undefined && (
        <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
          {helperText}
        </p>
      )}
    </label>
  );
}
