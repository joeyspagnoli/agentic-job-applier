/**
 * @packageDocumentation
 *
 * Compact inline error message used to surface mutation/query failures on the
 * settings page.
 */

import type { JSX } from "react";
import { COLOR_ERROR } from "@/lib/design-tokens";

/** Props for inline settings error text snippets. */
export interface InlineErrorTextProps {
  /** Error text content. */
  readonly message: string;
}

/**
 * Render one compact inline error message.
 *
 * @param props - Error message props.
 * @returns One styled error paragraph.
 */
export function InlineErrorText({ message }: InlineErrorTextProps): JSX.Element {
  return (
    <p className="text-sm" style={{ color: COLOR_ERROR }}>
      {message}
    </p>
  );
}
