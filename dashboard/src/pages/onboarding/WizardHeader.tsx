/**
 * @packageDocumentation
 *
 * Static header banner shown above the onboarding wizard's step content.
 *
 * @remarks
 * Pulled out of the page shell so the wizard's render path focuses on
 * step-driven UI rather than chrome.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";

/**
 * Render the welcome banner with the gradient bolt icon, title, and
 * one-line subhead.
 *
 * @returns The header element.
 */
export function WizardHeader(): JSX.Element {
  return (
    <div className="text-center mb-10">
      <div className="flex justify-center mb-4">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center signature-gradient">
          <span
            className="material-symbols-outlined text-white text-2xl"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            bolt
          </span>
        </div>
      </div>
      <h1
        className="text-fluid-2xl font-extrabold tracking-tight mb-2"
        style={{ color: COLOR_ON_SURFACE }}
      >
        Welcome to AutoApply
      </h1>
      <p className="text-fluid-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        Let&apos;s set up your job search profile in a few quick steps.
      </p>
    </div>
  );
}
