/**
 * @packageDocumentation
 *
 * Step 5 of the onboarding wizard: OpenAI API key entry plus an optional
 * Adzuna API-key section.
 *
 * @remarks
 * Adzuna is the API-backed replacement for the JobSpy Glassdoor scraper
 * (see issue #9). Both Adzuna fields are optional — the user can finish
 * onboarding without filling either, and partial fills are flagged with
 * an inline error so finish-flow validation can refuse to persist them.
 */

import type { JSX } from "react";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
} from "@/lib/design-tokens";
import type { ProviderDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepProvider}. */
export interface StepProviderProps {
  /** Current provider draft state. */
  readonly draft: ProviderDraft;
  /** Draft change handler. */
  readonly onChange: (next: ProviderDraft) => void;
}

/**
 * Step 5: OpenAI API key entry, with optional Adzuna data-source keys.
 *
 * @param props - {@link StepProviderProps}
 * @returns Two-section form: required OpenAI key + optional Adzuna pair.
 */
export function StepProvider({ draft, onChange }: StepProviderProps): JSX.Element {
  const adzunaIdFilled = draft.adzunaAppId.trim() !== "";
  const adzunaKeyFilled = draft.adzunaAppKey.trim() !== "";
  const adzunaPartial =
    (adzunaIdFilled && !adzunaKeyFilled) || (!adzunaIdFilled && adzunaKeyFilled);
  const inlineError = draft.adzunaError ?? (adzunaPartial
    ? "Provide both Adzuna fields or leave both blank."
    : undefined);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          OpenAI API Key
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          AutoApply uses OpenAI for resume tailoring and job scoring. Paste your API key
          below — it stays on your machine.
        </p>
      </div>
      <Field
        label="API Key"
        value={draft.apiKey}
        onChange={(v) => {
          onChange({ ...draft, apiKey: v });
        }}
        placeholder="sk-..."
        type="password"
      />
      <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        Get your key at{" "}
        <a
          href="https://platform.openai.com/api-keys"
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold underline"
        >
          platform.openai.com
        </a>
        .
      </p>

      <div
        className="pt-5 border-t"
        style={{ borderColor: COLOR_OUTLINE_VARIANT }}
      >
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Adzuna API
          </h3>
          <span
            className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border"
            style={{
              color: COLOR_ON_SURFACE_VARIANT,
              borderColor: COLOR_OUTLINE_VARIANT,
            }}
          >
            Optional
          </span>
        </div>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Adzuna is a free, API-backed alternative to scraping Glassdoor. Sign up
          at{" "}
          <a
            href="https://developer.adzuna.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold underline"
          >
            developer.adzuna.com
          </a>{" "}
          to grab an app ID and key. Leave both blank to skip.
        </p>
      </div>
      <Field
        label="Adzuna App ID"
        value={draft.adzunaAppId}
        onChange={(v) => {
          onChange({ ...draft, adzunaAppId: v, adzunaError: undefined });
        }}
        placeholder="e.g. a1b2c3d4"
        type="password"
      />
      <Field
        label="Adzuna App Key"
        value={draft.adzunaAppKey}
        onChange={(v) => {
          onChange({ ...draft, adzunaAppKey: v, adzunaError: undefined });
        }}
        placeholder="32-character secret"
        type="password"
      />
      {inlineError && (
        <p className="text-xs" style={{ color: COLOR_ERROR }} role="alert">
          {inlineError}
        </p>
      )}
    </div>
  );
}
