/**
 * @packageDocumentation
 *
 * Step 5 of the onboarding wizard: OpenAI API key entry.
 *
 * @remarks
 * The OSS launch ships with OpenAI BYOK as the only supported provider, so
 * this step is intentionally minimal — a single labelled password field
 * plus a hint pointing the user at the platform.openai.com key page. The
 * old Codex device-auth flow and the Anthropic/Gemini/OpenRouter chips
 * have been removed; reintroducing them is tracked by the wider-BYOK
 * follow-up issue.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
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
 * Step 5: OpenAI API key entry.
 *
 * @param props - {@link StepProviderProps}
 * @returns A single password field with a "where to get a key" hint.
 */
export function StepProvider({ draft, onChange }: StepProviderProps): JSX.Element {
  return (
    <div className="space-y-5">
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
          onChange({ apiKey: v });
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
    </div>
  );
}
