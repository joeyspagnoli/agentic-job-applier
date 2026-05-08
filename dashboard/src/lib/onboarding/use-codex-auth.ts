/**
 * @packageDocumentation
 *
 * `useCodexAuth` — encapsulates the start-and-poll device-auth flow used by
 * the AI provider step of the onboarding wizard.
 *
 * @remarks
 * The hook exposes a single `start` callback that initiates the device-auth
 * handshake and then polls `/codex/auth/status` every
 * {@link CODEX_POLL_INTERVAL_MS} ms until the auth completes or fails.
 * Status updates are written into the provider draft via the
 * {@link UseCodexAuthArgs.setProvider} setter, which the wizard already
 * uses for every other provider field — so no extra plumbing is required
 * to render auth state in {@link ../../pages/onboarding/StepProvider.StepProvider}.
 */

import { useCallback, useRef } from "react";
import { fetchCodexAuthStatus, startCodexAuth } from "@/lib/api/client";
import { CODEX_POLL_INTERVAL_MS } from "./constants";
import type { ProviderDraft } from "./types";

/** Argument bundle for {@link useCodexAuth}. */
export interface UseCodexAuthArgs {
  /**
   * State updater for the provider draft. Accepts the same updater shape
   * as `useState`'s setter so the hook can patch fields without owning the
   * full draft.
   */
  readonly setProvider: (next: (prev: ProviderDraft) => ProviderDraft) => void;
}

/** Return value of {@link useCodexAuth}. */
export interface UseCodexAuthResult {
  /**
   * Start the Codex device-auth handshake and begin polling.
   *
   * @returns A promise that resolves once the initial start request settles.
   *   Polling continues asynchronously after the promise resolves.
   */
  readonly start: () => Promise<void>;
}

/**
 * React hook that owns Codex device-auth lifecycle.
 *
 * @param args - {@link UseCodexAuthArgs}
 * @returns The `start` callback to wire to the "Sign in with Codex" button.
 */
export function useCodexAuth({ setProvider }: UseCodexAuthArgs): UseCodexAuthResult {
  const intervalRef = useRef<number | null>(null);

  const poll = useCallback((): void => {
    const intervalId = window.setInterval(async () => {
      try {
        const status = await fetchCodexAuthStatus();
        setProvider((prev) => ({
          ...prev,
          codexStatus: status.status,
          codexUrl: status.verification_url ?? prev.codexUrl,
          codexCode: status.device_code ?? prev.codexCode,
        }));

        if (status.status === "completed" || status.status === "failed") {
          window.clearInterval(intervalId);
        }
      } catch {
        window.clearInterval(intervalId);
        setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
      }
    }, CODEX_POLL_INTERVAL_MS);
    intervalRef.current = intervalId;
  }, [setProvider]);

  const start = useCallback(async (): Promise<void> => {
    setProvider((prev) => ({ ...prev, codexStatus: "starting" }));

    try {
      const snapshot = await startCodexAuth();
      setProvider((prev) => ({
        ...prev,
        codexStatus: snapshot.status === "running" ? "running" : "starting",
        codexUrl: snapshot.verification_url,
        codexCode: snapshot.device_code,
      }));

      poll();
    } catch {
      setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
    }
  }, [poll, setProvider]);

  return { start };
}
