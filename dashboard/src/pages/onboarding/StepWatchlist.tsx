/**
 * @packageDocumentation
 *
 * Step 6 of the onboarding wizard: optional company watchlist.
 */

import type { JSX } from "react";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
} from "@/lib/design-tokens";
import type { WatchlistDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepWatchlist}. */
export interface StepWatchlistProps {
  /** Current watchlist draft. */
  readonly draft: WatchlistDraft;
  /** Replace the draft with `next`. */
  readonly onChange: (next: WatchlistDraft) => void;
}

/**
 * Step 6: Optional company watchlist.
 *
 * @param props - {@link StepWatchlistProps}
 * @returns Watchlist form.
 */
export function StepWatchlist({ draft, onChange }: StepWatchlistProps): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Company Watchlist
          <span
            className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full"
            style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
          >
            Optional
          </span>
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Add specific companies to track. Their career pages will be scanned for new openings.
        </p>
      </div>
      <Field
        label="Companies (one per line)"
        value={draft.companies}
        onChange={(v) => {
          onChange({ ...draft, companies: v });
        }}
        placeholder="Stripe&#10;Notion&#10;Linear&#10;Vercel"
        multiline
      />
    </div>
  );
}
