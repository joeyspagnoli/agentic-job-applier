/**
 * @packageDocumentation
 *
 * Pill-shaped step indicator at the top of the onboarding wizard.
 *
 * @remarks
 * Lets the user click any prior step to revisit it; future steps stay
 * disabled so partially-filled drafts are not skipped past.
 */

import type { JSX } from "react";
import {
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
} from "@/lib/design-tokens";
import { STEP_COUNT, STEP_LABELS } from "@/lib/onboarding/constants";

/** Props for {@link ProgressIndicator}. */
export interface ProgressIndicatorProps {
  /** Index of the step currently being edited. */
  readonly currentStep: number;
  /**
   * Called when the user clicks a step button. Implementations should ignore
   * forward navigation since the parent enforces "no skipping unfilled steps".
   */
  readonly onStepClick: (stepIndex: number) => void;
}

/**
 * Render the step pills with checkmarks for completed steps and a connecting
 * line between adjacent pills.
 *
 * @param props - {@link ProgressIndicatorProps}
 * @returns Progress indicator element.
 */
export function ProgressIndicator({
  currentStep,
  onStepClick,
}: ProgressIndicatorProps): JSX.Element {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {STEP_LABELS.map((label, idx) => (
        <div key={label} className="flex items-center gap-2">
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200"
            style={{
              backgroundColor:
                idx === currentStep
                  ? COLOR_PRIMARY
                  : idx < currentStep
                    ? COLOR_PRIMARY_FIXED
                    : "transparent",
              color:
                idx === currentStep
                  ? "#ffffff"
                  : idx < currentStep
                    ? COLOR_PRIMARY
                    : COLOR_OUTLINE,
            }}
            onClick={() => {
              if (idx <= currentStep) {
                onStepClick(idx);
              }
            }}
          >
            {idx < currentStep ? (
              <span className="material-symbols-outlined text-[14px]">check</span>
            ) : (
              <span className="text-[11px] font-bold">{idx + 1}</span>
            )}
            <span className="hidden sm:inline">{label}</span>
          </button>
          {idx < STEP_COUNT - 1 && (
            <div
              className="w-6 h-px"
              style={{
                backgroundColor: idx < currentStep ? COLOR_PRIMARY : COLOR_OUTLINE_VARIANT,
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
