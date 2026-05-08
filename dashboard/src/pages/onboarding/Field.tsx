/**
 * @packageDocumentation
 *
 * Reusable labeled form field used by every onboarding step component.
 *
 * @remarks
 * A thin wrapper over `<input>` and `<textarea>` that keeps presentation
 * concerns (rounded border, focus ring, required asterisk) in one place
 * so each step component focuses on which fields it composes rather than
 * how they look.
 */

import type { JSX } from "react";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";

/** Props for an individual form input. */
export interface FieldProps {
  /** Label text above the input. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Change callback. */
  readonly onChange: (value: string) => void;
  /** Input placeholder. */
  readonly placeholder?: string;
  /** Input type. */
  readonly type?: string;
  /** Whether to render a textarea instead. */
  readonly multiline?: boolean;
  /** Whether the field is required. */
  readonly required?: boolean;
}

/**
 * Reusable form field with label.
 *
 * @param props - {@link FieldProps}
 * @returns Labeled input element.
 */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  multiline,
  required,
}: FieldProps): JSX.Element {
  const inputClasses =
    "w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors focus:ring-2 focus:ring-primary/30";
  const inputStyle = {
    borderColor: COLOR_OUTLINE_VARIANT,
    color: COLOR_ON_SURFACE,
    backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
  };

  return (
    <label className="block">
      <span
        className="text-xs font-semibold mb-1.5 block"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
      >
        {label}
        {required && <span style={{ color: COLOR_ERROR }}> *</span>}
      </span>
      {multiline ? (
        <textarea
          className={inputClasses}
          style={inputStyle}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          placeholder={placeholder}
          rows={4}
        />
      ) : (
        <input
          className={inputClasses}
          style={inputStyle}
          type={type}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}
