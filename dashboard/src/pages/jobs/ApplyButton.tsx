/**
 * @packageDocumentation
 *
 * Apply button for one jobs row, covering all six run lifecycle states.
 *
 * @remarks
 * State machine driven entirely by the `tailorRun` and `applyRun` props —
 * no internal async logic. The caller owns mutations and passes callbacks.
 */

import type { JSX } from "react";
import type { TailorRunSummaryModel } from "@/lib/api/adapters";
import type { ApplyRunDto } from "@/lib/api/types";
import {
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Tailwind classes for the amber "needs review" badge state. */
const CLASS_AMBER_BADGE = "rounded-xl px-4 py-2 text-xs font-bold bg-amber-100 text-amber-800" as const;

/** Tailwind classes for the green "auto-applied" badge state. */
const CLASS_GREEN_BADGE = "rounded-xl px-4 py-2 text-xs font-bold bg-green-100 text-green-800" as const;

/** Tailwind classes for the standard action button. */
const CLASS_ACTION_BUTTON =
  "px-4 py-2 rounded-xl text-xs font-bold text-white transition-all scale-98-on-click disabled:opacity-60" as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Props accepted by {@link ApplyButton}. */
export interface ApplyButtonProps {
  /** Stable deduplication hash of the job being acted upon. */
  readonly jobHash: string;
  /** Embedded tailor-run snapshot from the parent row, or null if none exists. */
  readonly tailorRun: TailorRunSummaryModel | null;
  /** Current apply run for this job, or null if none has been created. */
  readonly applyRun: ApplyRunDto | null;
  /**
   * Callback fired when the user chooses to apply without tailoring.
   *
   * @remarks
   * Caller should POST `/api/jobs/{jobHash}/apply` and then invalidate
   * the jobs query to refresh this row.
   */
  readonly onApply: () => void;
  /**
   * Callback fired when the user chooses to tailor first, then apply.
   *
   * @remarks
   * Caller should POST tailor, poll until SUCCESS, then POST apply.
   */
  readonly onTailorThenApply: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Determine whether the tailor run is still in progress.
 *
 * @param tailorRun - Nullable tailor run snapshot.
 * @returns True when tailor is PENDING or RUNNING.
 */
function isTailorInProgress(tailorRun: TailorRunSummaryModel | null): boolean {
  if (tailorRun === null) return false;
  return tailorRun.status === "PENDING" || tailorRun.status === "RUNNING";
}

/**
 * Determine whether the apply run is still in progress.
 *
 * @param applyRun - Nullable apply run DTO.
 * @returns True when apply is PENDING or RUNNING.
 */
function isApplyInProgress(applyRun: ApplyRunDto | null): boolean {
  if (applyRun === null) return false;
  return applyRun.status === "PENDING" || applyRun.status === "RUNNING";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render the apply action control for one job row.
 *
 * @remarks
 * Six mutually exclusive states, evaluated in priority order:
 *
 * 1. Tailor PENDING/RUNNING → "Waiting on tailor run #N…" (disabled).
 * 2. Apply PENDING/RUNNING  → "Applying…" (disabled).
 * 3. Apply SUCCESS + NEEDS_REVIEW → amber badge.
 * 4. Apply SUCCESS + SUBMITTED   → green badge.
 * 5. Apply FAILED          → "Apply failed — retry" (re-clickable).
 * 6. No apply run          → "Apply" (opens {@link NotTailoredModal}).
 *
 * @param props - {@link ApplyButtonProps}
 * @returns The appropriate button or badge for the current state.
 */
export function ApplyButton({
  tailorRun,
  applyRun,
  onApply,
  onTailorThenApply,
}: ApplyButtonProps): JSX.Element {
  // State 2 — tailor is running; apply cannot proceed yet.
  if (isTailorInProgress(tailorRun)) {
    return (
      <button
        type="button"
        className={CLASS_ACTION_BUTTON}
        style={{ backgroundColor: COLOR_PRIMARY }}
        disabled
      >
        Waiting on tailor run #{tailorRun!.id}…
      </button>
    );
  }

  // State 3 — apply is running.
  if (isApplyInProgress(applyRun)) {
    return (
      <button
        type="button"
        className={CLASS_ACTION_BUTTON}
        style={{ backgroundColor: COLOR_PRIMARY }}
        disabled
      >
        Applying…
      </button>
    );
  }

  // States driven by a completed apply run.
  if (applyRun !== null) {
    if (applyRun.status === "SUCCESS") {
      if (applyRun.outcome === "NEEDS_REVIEW") {
        return <span className={CLASS_AMBER_BADGE}>Applied — needs review</span>;
      }
      if (applyRun.outcome === "SUBMITTED") {
        return <span className={CLASS_GREEN_BADGE}>Auto-applied</span>;
      }
    }

    if (applyRun.status === "FAILED") {
      return (
        <button
          type="button"
          className={CLASS_ACTION_BUTTON}
          style={{ backgroundColor: COLOR_OUTLINE_VARIANT, color: COLOR_ON_SURFACE_VARIANT }}
          onClick={onApply}
        >
          Apply failed — retry
        </button>
      );
    }
  }

  // State 1 — idle; no apply run of any kind.
  return (
    <button
      type="button"
      className={CLASS_ACTION_BUTTON}
      style={{ backgroundColor: COLOR_PRIMARY }}
      onClick={onTailorThenApply}
    >
      Apply
    </button>
  );
}
