/**
 * @packageDocumentation
 *
 * Back / Skip / Continue / Finish footer for the onboarding wizard.
 *
 * @remarks
 * Renders the Skip button only on optional steps (steps 2+), and swaps
 * "Continue" for "Finish Setup" on the final step. Disabled states are
 * driven entirely by parent props so this component owns no state of
 * its own.
 */

import type { JSX } from "react";
import {
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";
import { STEP_COUNT } from "@/lib/onboarding/constants";

/** Props for {@link NavigationButtons}. */
export interface NavigationButtonsProps {
  /** Index of the step currently being edited. */
  readonly currentStep: number;
  /** Whether the user may advance to the next step. */
  readonly canAdvance: boolean;
  /** Whether the wizard is currently persisting onboarding data. */
  readonly saving: boolean;
  /** Go back one step. */
  readonly onBack: () => void;
  /** Advance one step. */
  readonly onNext: () => void;
  /** Submit the wizard. */
  readonly onFinish: () => void;
}

/**
 * Render the bottom navigation row.
 *
 * @param props - {@link NavigationButtonsProps}
 * @returns Navigation bar element.
 */
export function NavigationButtons({
  currentStep,
  canAdvance,
  saving,
  onBack,
  onNext,
  onFinish,
}: NavigationButtonsProps): JSX.Element {
  const isLastStep = currentStep >= STEP_COUNT - 1;
  const showSkip = !isLastStep && currentStep >= 2;

  return (
    <div
      className="flex justify-between items-center mt-8 pt-6 border-t"
      style={{ borderColor: `${COLOR_OUTLINE_VARIANT}30` }}
    >
      <button
        className="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
        style={{
          color: currentStep === 0 ? COLOR_OUTLINE : COLOR_ON_SURFACE_VARIANT,
          opacity: currentStep === 0 ? 0.4 : 1,
        }}
        disabled={currentStep === 0}
        onClick={onBack}
      >
        Back
      </button>

      <div className="flex gap-3">
        {showSkip && (
          <button
            className="px-4 py-2 rounded-xl text-sm font-medium transition-colors"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onClick={onNext}
          >
            Skip
          </button>
        )}
        {!isLastStep ? (
          <button
            className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
            style={{ backgroundColor: COLOR_PRIMARY }}
            disabled={!canAdvance}
            onClick={onNext}
          >
            Continue
          </button>
        ) : (
          <button
            className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
            style={{ backgroundColor: COLOR_PRIMARY }}
            disabled={saving}
            onClick={onFinish}
          >
            {saving ? "Saving..." : "Finish Setup"}
          </button>
        )}
      </div>
    </div>
  );
}
