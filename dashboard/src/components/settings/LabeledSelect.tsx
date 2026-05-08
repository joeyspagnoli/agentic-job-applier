/**
 * @packageDocumentation
 *
 * Labeled dropdown select used throughout the guided settings forms.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE_VARIANT, COLOR_OUTLINE } from "@/lib/design-tokens";
import type { SelectOption } from "@/lib/settings/types";

/** Props for labeled select input. */
export interface LabeledSelectProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
  /** Select options in display order. */
  readonly options: readonly SelectOption[];
  /** Optional helper text shown below select. */
  readonly helperText?: string;
}

/**
 * Render one labeled select input.
 *
 * @param props - Labeled select props.
 * @returns One select field block.
 */
export function LabeledSelect({
  label,
  value,
  onChange,
  options,
  helperText,
}: LabeledSelectProps): JSX.Element {
  return (
    <label className="block text-xs font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
      {label}
      <select
        className="mt-1 w-full rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {options.map((option) => (
          <option key={`${label}-${option.value}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {helperText !== undefined && (
        <p className="mt-1 text-xs" style={{ color: COLOR_OUTLINE }}>
          {helperText}
        </p>
      )}
    </label>
  );
}
