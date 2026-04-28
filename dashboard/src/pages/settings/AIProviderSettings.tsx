/**
 * @packageDocumentation
 *
 * AI provider settings section with Codex device auth and BYOK configuration.
 *
 * @remarks
 * Replaces the per-key API key management with a unified provider model.
 * Two modes: Codex (OAuth device auth) or BYOK (single API key for all stages).
 */

import type { JSX } from "react";
import { useState, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAiProviderSettings,
  updateAiProviderSettings,
  startCodexAuth,
  fetchCodexAuthStatus,
  disconnectCodexAuth,
} from "@/lib/api/client";
import type { AiProviderMode, AiProviderType, CodexAuthSnapshotDto } from "@/lib/api/client";
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

/** Interval in ms between Codex auth status polls. */
const CODEX_POLL_INTERVAL_MS = 3000;

/** BYOK provider options. */
const PROVIDER_OPTIONS: readonly { value: AiProviderType; label: string; placeholder: string }[] = [
  { value: "openai", label: "OpenAI", placeholder: "sk-..." },
  { value: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
  { value: "gemini", label: "Google Gemini", placeholder: "AIza..." },
  { value: "openrouter", label: "OpenRouter", placeholder: "sk-or-..." },
];

/**
 * AI provider settings section component.
 *
 * @remarks
 * Embeddable within the settings page as a tab section. Manages both
 * Codex device auth and BYOK API key configuration.
 *
 * @returns The AI provider settings form.
 */
export function AIProviderSettings(): JSX.Element {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AiProviderMode>("byok");
  const [providerType, setProviderType] = useState<AiProviderType>("openai");
  const [apiKey, setApiKey] = useState<string>("");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const [codexSnapshot, setCodexSnapshot] = useState<CodexAuthSnapshotDto | null>(null);
  const codexPollRef = useRef<number | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["ai-provider-settings"],
    queryFn: fetchAiProviderSettings,
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setMode(settingsQuery.data.mode);
      if (settingsQuery.data.provider_type) {
        setProviderType(settingsQuery.data.provider_type);
      }
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (payload: { mode: AiProviderMode; provider_type?: AiProviderType; api_key?: string }) =>
      updateAiProviderSettings(payload),
    onSuccess: () => {
      setSaveStatus("saved");
      setSaveError(null);
      void queryClient.invalidateQueries({ queryKey: ["ai-provider-settings"] });
      window.setTimeout(() => { setSaveStatus("idle"); }, 2000);
    },
    onError: (err: Error) => {
      setSaveStatus("error");
      setSaveError(err.message);
    },
  });

  /**
   * Save BYOK configuration.
   *
   * @returns Nothing.
   */
  function handleSaveBYOK(): void {
    setSaveStatus("saving");
    saveMutation.mutate({
      mode: "byok",
      provider_type: providerType,
      api_key: apiKey.trim() !== "" ? apiKey : undefined,
    });
  }

  /**
   * Start Codex device auth flow and begin polling.
   *
   * @returns Nothing.
   */
  async function handleStartCodex(): Promise<void> {
    try {
      const snapshot = await startCodexAuth();
      setCodexSnapshot(snapshot);
      startCodexPolling();
    } catch (err: unknown) {
      setCodexSnapshot({
        status: "failed",
        verification_url: null,
        device_code: null,
        error_message: err instanceof Error ? err.message : "Failed to start auth",
      });
    }
  }

  /**
   * Poll Codex auth status until terminal state.
   *
   * @returns Nothing.
   */
  function startCodexPolling(): void {
    stopCodexPolling();
    codexPollRef.current = window.setInterval(async () => {
      try {
        const status = await fetchCodexAuthStatus();
        setCodexSnapshot(status);
        if (status.status === "completed" || status.status === "failed") {
          stopCodexPolling();
          if (status.status === "completed") {
            setMode("codex");
            saveMutation.mutate({ mode: "codex" });
          }
        }
      } catch {
        stopCodexPolling();
      }
    }, CODEX_POLL_INTERVAL_MS);
  }

  /**
   * Stop polling for Codex auth status.
   *
   * @returns Nothing.
   */
  function stopCodexPolling(): void {
    if (codexPollRef.current !== null) {
      window.clearInterval(codexPollRef.current);
      codexPollRef.current = null;
    }
  }

  useEffect(() => {
    return () => { stopCodexPolling(); };
  }, []);

  /**
   * Disconnect from Codex and switch to BYOK mode.
   *
   * @returns Nothing.
   */
  async function handleDisconnectCodex(): Promise<void> {
    try {
      await disconnectCodexAuth();
      setCodexSnapshot(null);
      setMode("byok");
      void queryClient.invalidateQueries({ queryKey: ["ai-provider-settings"] });
    } catch {
      setSaveError("Failed to disconnect");
    }
  }

  const isCodexActive = settingsQuery.data?.mode === "codex" && settingsQuery.data?.is_configured;
  const codexIsPolling = codexSnapshot?.status === "starting" || codexSnapshot?.status === "running";

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-bold" style={{ color: COLOR_ON_SURFACE }}>
          AI Provider
        </h3>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Configure how AutoApply accesses AI models for job scoring and resume tailoring.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="grid grid-cols-2 gap-3">
        <button
          className="flex items-center gap-3 p-4 rounded-xl border transition-all text-left"
          style={{
            backgroundColor: mode === "codex" ? COLOR_PRIMARY_FIXED : "transparent",
            borderColor: mode === "codex" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => { setMode("codex"); }}
        >
          <span
            className="material-symbols-outlined text-xl"
            style={{ color: mode === "codex" ? COLOR_PRIMARY : COLOR_OUTLINE }}
          >
            cloud
          </span>
          <div>
            <p className="text-sm font-bold" style={{ color: mode === "codex" ? COLOR_PRIMARY : COLOR_ON_SURFACE }}>
              Codex Subscription
            </p>
            <p className="text-xs mt-0.5" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Sign in with your OpenAI account
            </p>
          </div>
        </button>

        <button
          className="flex items-center gap-3 p-4 rounded-xl border transition-all text-left"
          style={{
            backgroundColor: mode === "byok" ? COLOR_PRIMARY_FIXED : "transparent",
            borderColor: mode === "byok" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => { setMode("byok"); }}
        >
          <span
            className="material-symbols-outlined text-xl"
            style={{ color: mode === "byok" ? COLOR_PRIMARY : COLOR_OUTLINE }}
          >
            key
          </span>
          <div>
            <p className="text-sm font-bold" style={{ color: mode === "byok" ? COLOR_PRIMARY : COLOR_ON_SURFACE }}>
              Bring Your Own Key
            </p>
            <p className="text-xs mt-0.5" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              One API key for all pipeline stages
            </p>
          </div>
        </button>
      </div>

      {/* Codex auth section */}
      {mode === "codex" && (
        <div
          className="rounded-xl border p-5 space-y-4"
          style={{
            borderColor: `${COLOR_OUTLINE_VARIANT}40`,
            backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
          }}
        >
          {isCodexActive && !codexIsPolling && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-lg" style={{ color: COLOR_SUCCESS }}>
                  check_circle
                </span>
                <span className="text-sm font-semibold" style={{ color: COLOR_SUCCESS }}>
                  Codex connected
                </span>
              </div>
              <button
                className="text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors"
                style={{ color: COLOR_ERROR, borderColor: `${COLOR_ERROR}40` }}
                onClick={() => { void handleDisconnectCodex(); }}
              >
                Disconnect
              </button>
            </div>
          )}

          {!isCodexActive && !codexIsPolling && codexSnapshot?.status !== "failed" && (
            <>
              <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Sign in with your Codex/OpenAI subscription. A verification URL and one-time code will appear below.
              </p>
              <button
                className="px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={() => { void handleStartCodex(); }}
              >
                Sign in with Codex
              </button>
            </>
          )}

          {codexIsPolling && codexSnapshot && (
            <div className="space-y-3">
              <p className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
                Waiting for authentication...
              </p>
              {codexSnapshot.verification_url && (
                <>
                  <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    Open this URL in your browser and enter the code:
                  </p>
                  <a
                    href={codexSnapshot.verification_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-semibold underline block"
                    style={{ color: COLOR_PRIMARY }}
                  >
                    {codexSnapshot.verification_url}
                  </a>
                </>
              )}
              {codexSnapshot.device_code && (
                <div
                  className="inline-block px-4 py-2 rounded-lg font-mono text-lg font-bold tracking-widest"
                  style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
                >
                  {codexSnapshot.device_code}
                </div>
              )}
              <p className="text-xs animate-pulse" style={{ color: COLOR_OUTLINE }}>
                Polling every {CODEX_POLL_INTERVAL_MS / 1000}s...
              </p>
            </div>
          )}

          {codexSnapshot?.status === "failed" && (
            <div className="space-y-2">
              <p className="text-sm font-medium" style={{ color: COLOR_ERROR }}>
                {codexSnapshot.error_message ?? "Authentication failed"}
              </p>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-white"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={() => { void handleStartCodex(); }}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}

      {/* BYOK section */}
      {mode === "byok" && (
        <div className="space-y-4">
          <div>
            <span className="text-xs font-semibold mb-2 block" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Provider
            </span>
            <div className="flex flex-wrap gap-2">
              {PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all"
                  style={{
                    backgroundColor: providerType === p.value ? COLOR_PRIMARY_FIXED : "transparent",
                    color: providerType === p.value ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                    borderColor: providerType === p.value ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
                  }}
                  onClick={() => { setProviderType(p.value); }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="text-xs font-semibold mb-1.5 block" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              API Key
            </span>
            <input
              className="w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors"
              style={{
                borderColor: COLOR_OUTLINE_VARIANT,
                color: COLOR_ON_SURFACE,
                backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
              }}
              type="password"
              value={apiKey}
              onChange={(e) => { setApiKey(e.target.value); }}
              placeholder={PROVIDER_OPTIONS.find((p) => p.value === providerType)?.placeholder ?? "API key"}
            />
            {settingsQuery.data?.is_configured && settingsQuery.data.mode === "byok" && (
              <p className="text-xs mt-1" style={{ color: COLOR_SUCCESS }}>
                Key is configured. Enter a new value to replace it.
              </p>
            )}
          </label>

          <div className="flex items-center gap-3">
            <button
              className="px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click disabled:opacity-50"
              style={{ backgroundColor: COLOR_PRIMARY }}
              disabled={saveMutation.isPending}
              onClick={handleSaveBYOK}
            >
              {saveMutation.isPending ? "Saving..." : "Save Provider"}
            </button>
            {saveStatus === "saved" && (
              <span className="text-xs font-semibold" style={{ color: COLOR_SUCCESS }}>
                Saved
              </span>
            )}
            {saveStatus === "error" && saveError && (
              <span className="text-xs font-semibold" style={{ color: COLOR_ERROR }}>
                {saveError}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
