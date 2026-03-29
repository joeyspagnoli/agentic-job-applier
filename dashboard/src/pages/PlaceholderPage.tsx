/**
 * @packageDocumentation
 *
 * Temporary placeholder rendered for pages that have not been implemented yet.
 *
 * @remarks
 * Replace each usage in `App.tsx` with the real page component once it is built.
 * Scaffolded pages: Jobs, Human Review, Failures, Cost Tracking.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE_VARIANT, COLOR_OUTLINE_VARIANT } from "@/lib/design-tokens";

/** Props accepted by the {@link PlaceholderPage} component. */
interface PlaceholderPageProps {
  /** The page name displayed in the placeholder message. */
  readonly name: string;
}

/**
 * Renders a centered "coming soon" message for unimplemented pages.
 *
 * @param props - {@link PlaceholderPageProps}
 * @returns A centered placeholder element.
 */
export function PlaceholderPage({ name }: PlaceholderPageProps): JSX.Element {
  return (
    <div className="p-8 flex items-center justify-center h-64">
      <div className="text-center">
        <span
          className="material-symbols-outlined text-6xl mb-4 block"
          style={{ color: COLOR_OUTLINE_VARIANT }}
        >
          construction
        </span>
        <p className="font-medium" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {name} — coming soon
        </p>
      </div>
    </div>
  );
}
