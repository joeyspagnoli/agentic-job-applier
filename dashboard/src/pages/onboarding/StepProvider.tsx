/**
 * @packageDocumentation
 *
 * Step 5 of the onboarding wizard: AI provider selection (Codex device-auth
 * or BYOK).
 */

import type { JSX } from "react";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SUCCESS,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";
import type { AiProviderType } from "@/lib/api/client";
import type { ProviderDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** BYOK provider options shown in the picker chip group. */
const PROVIDER_OPTIONS: readonly { value: AiProviderType; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Google Gemini" },
  { value: "openrouter", label: "OpenRouter" },
];

/** Props for {@link StepProvider}. */
export interface StepProviderProps {
  /** Current provider draft state. */
  readonly draft: ProviderDraft;
  /** Draft change handler. */
  readonly onChange: (next: ProviderDraft) => void;
  /** Callback to initiate Codex device auth. */
  readonly onStartCodex: () => void;
}

/**
 * Step 5: AI provider configuration.
 *
 * @param props - {@link StepProviderProps}
 * @returns AI provider setup form.
 */
export function StepProvider({ draft, onChange, onStartCodex }: StepProviderProps): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          AI Provider
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Choose how AutoApply accesses AI for resume tailoring and job scoring.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "codex" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "codex" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "codex" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => {
            onChange({ ...draft, mode: "codex" });
          }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">cloud</span>
          Codex (Subscription)
        </button>
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "byok" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "byok" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "byok" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => {
            onChange({ ...draft, mode: "byok" });
          }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">key</span>
          Bring Your Own Key
        </button>
      </div>

      {draft.mode === "codex" && (
        <div
          className="rounded-xl p-5 border"
          style={{
            borderColor: `${COLOR_OUTLINE_VARIANT}40`,
            backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
          }}
        >
          {draft.codexStatus === "idle" && (
            <>
              <p className="text-sm mb-3" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Sign in with your Codex/OpenAI subscription. A browser window will open for
                authentication.
              </p>
              <button
                className="px-5 py-2 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Sign in with Codex
              </button>
            </>
          )}
          {(draft.codexStatus === "starting" || draft.codexStatus === "running") && (
            <div className="space-y-3">
              <p className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
                Waiting for authentication...
              </p>
              {draft.codexUrl && (
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Open this URL and enter the code below:
                </p>
              )}
              {draft.codexUrl && (
                <a
                  href={draft.codexUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold underline"
                  style={{ color: COLOR_PRIMARY }}
                >
                  {draft.codexUrl}
                </a>
              )}
              {draft.codexCode && (
                <div
                  className="inline-block px-4 py-2 rounded-lg font-mono text-lg font-bold tracking-widest"
                  style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
                >
                  {draft.codexCode}
                </div>
              )}
              <p className="text-xs animate-pulse" style={{ color: COLOR_OUTLINE }}>
                Polling for completion...
              </p>
            </div>
          )}
          {draft.codexStatus === "completed" && (
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-lg" style={{ color: COLOR_SUCCESS }}>
                check_circle
              </span>
              <span className="text-sm font-semibold" style={{ color: COLOR_SUCCESS }}>
                Codex authentication complete
              </span>
            </div>
          )}
          {draft.codexStatus === "failed" && (
            <div className="space-y-2">
              <p className="text-sm font-medium" style={{ color: COLOR_ERROR }}>
                Authentication failed. Please try again.
              </p>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-white"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}

      {draft.mode === "byok" && (
        <div className="space-y-4">
          <div>
            <span
              className="text-xs font-semibold mb-2 block"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Provider
            </span>
            <div className="flex flex-wrap gap-2">
              {PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all"
                  style={{
                    backgroundColor:
                      draft.providerType === p.value ? COLOR_PRIMARY_FIXED : "transparent",
                    color:
                      draft.providerType === p.value ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                    borderColor:
                      draft.providerType === p.value ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
                  }}
                  onClick={() => {
                    onChange({ ...draft, providerType: p.value });
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
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
        </div>
      )}
    </div>
  );
}
