/**
 * @packageDocumentation
 *
 * Custom React hook for streaming Server-Sent Events (SSE) from the
 * AutoApply pipeline progress endpoint.
 *
 * @remarks
 * Uses streaming `fetch` (not `EventSource`) so that custom auth headers
 * can be attached to the request. Automatically reconnects after a 5-second
 * delay when the connection drops unexpectedly. Heartbeat events (empty
 * `data:` lines) are silently ignored.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Shape of a single SSE pipeline progress event. */
export interface PipelineEvent {
  /** Current pipeline stage identifier (e.g. "fetching", "scoring", "applying"). */
  readonly stage: string;
  /** Job board source being processed (e.g. "greenhouse", "lever"). */
  readonly source: string;
  /** Normalised progress value in the 0-1 range. */
  readonly progress: number;
  /** Cumulative count of jobs discovered so far. */
  readonly jobsFound: number;
  /** List of error messages encountered during this stage. */
  readonly errors: string[];
  /** Client-side reception timestamp in milliseconds since epoch. */
  readonly timestamp: number;
}

/** Return value of the {@link useSSE} hook. */
export interface UseSSEReturn {
  /** Ordered list of all pipeline events received during this connection. */
  readonly events: PipelineEvent[];
  /** Whether the SSE stream is currently open and receiving data. */
  readonly isConnected: boolean;
  /** Human-readable error message, or `null` when healthy. */
  readonly error: string | null;
  /** Manually open the SSE connection. */
  readonly connect: () => void;
  /** Manually close the SSE connection and cancel auto-reconnect. */
  readonly disconnect: () => void;
}

/** Endpoint path for pipeline progress SSE stream. */
const SSE_ENDPOINT = "/api/pipeline/progress" as const;

/** Milliseconds to wait before attempting reconnection. */
const RECONNECT_DELAY_MS = 5_000 as const;

/**
 * Attempt to parse a raw SSE `data:` payload into a {@link PipelineEvent}.
 *
 * @param raw - The trimmed string content after `data: `.
 * @returns A fully-typed event on success, or `null` when the payload is a
 *          heartbeat or cannot be parsed.
 */
function parseSsePayload(raw: string): PipelineEvent | null {
  if (raw === "" || raw === "\n") {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);

    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }

    const record = parsed as Record<string, unknown>;

    return {
      stage: typeof record.stage === "string" ? record.stage : "",
      source: typeof record.source === "string" ? record.source : "",
      progress: typeof record.progress === "number" ? record.progress : 0,
      jobsFound: typeof record.jobsFound === "number" ? record.jobsFound : 0,
      errors: Array.isArray(record.errors)
        ? (record.errors as unknown[]).filter((e): e is string => typeof e === "string")
        : [],
      timestamp: Date.now(),
    };
  } catch {
    return null;
  }
}

/**
 * Stream pipeline progress events over SSE using `fetch`.
 *
 * @remarks
 * The hook manages its own lifecycle: it connects on mount, parses
 * incoming `data:` frames, accumulates events in state, and auto-
 * reconnects after unexpected disconnection. Call `disconnect()` to
 * permanently tear down the stream until `connect()` is invoked again.
 *
 * @returns A {@link UseSSEReturn} object with live event state and
 *          imperative connection controls.
 *
 * @example
 * ```tsx
 * const { events, isConnected } = useSSE();
 * const latest = events.at(-1);
 * ```
 */
export function useSSE(): UseSSEReturn {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  /** Abort controller for the active fetch request. */
  const abortControllerRef = useRef<AbortController | null>(null);

  /** Timer handle for scheduled reconnection attempts. */
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** When true the user has explicitly disconnected; suppress auto-reconnect. */
  const manuallyDisconnectedRef = useRef<boolean>(false);

  /**
   * Clear any pending reconnect timer.
   */
  const clearReconnectTimer = useCallback((): void => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  /**
   * Open the SSE connection and begin consuming events.
   *
   * Safe to call multiple times; redundant calls are no-ops when a
   * connection is already active.
   */
  const connect = useCallback((): void => {
    // Tear down any prior connection first.
    if (abortControllerRef.current !== null) {
      abortControllerRef.current.abort();
    }
    clearReconnectTimer();
    manuallyDisconnectedRef.current = false;

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setError(null);

    /**
     * Internal async routine that performs the streaming fetch and
     * feeds parsed events into React state.
     */
    async function startStream(): Promise<void> {
      try {
        const response = await fetch(SSE_ENDPOINT, {
          method: "GET",
          headers: {
            Accept: "text/event-stream",
            "Cache-Control": "no-cache",
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`SSE connection failed with status ${String(response.status)}`);
        }

        if (response.body === null) {
          throw new Error("SSE response body is null");
        }

        setIsConnected(true);
        setError(null);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });

          // SSE frames are terminated by a double newline.
          const frames = buffer.split("\n\n");
          // The last element is either empty or an incomplete frame.
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            const lines = frame.split("\n");

            for (const line of lines) {
              if (line.startsWith("data:")) {
                const payload = line.slice("data:".length).trim();
                const event = parseSsePayload(payload);

                if (event !== null) {
                  setEvents((previous) => [...previous, event]);
                }
              }
              // Ignore comment lines (starting with `:`) and other fields.
            }
          }
        }
      } catch (caughtError: unknown) {
        // AbortError is expected when the user disconnects manually.
        if (caughtError instanceof DOMException && caughtError.name === "AbortError") {
          return;
        }

        const message =
          caughtError instanceof Error ? caughtError.message : "Unknown SSE error";
        setError(message);
      } finally {
        setIsConnected(false);

        // Schedule auto-reconnect unless the user explicitly disconnected.
        if (!manuallyDisconnectedRef.current) {
          reconnectTimerRef.current = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY_MS);
        }
      }
    }

    void startStream();
  }, [clearReconnectTimer]);

  /**
   * Close the SSE connection and suppress automatic reconnection.
   */
  const disconnect = useCallback((): void => {
    manuallyDisconnectedRef.current = true;
    clearReconnectTimer();

    if (abortControllerRef.current !== null) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setIsConnected(false);
  }, [clearReconnectTimer]);

  // Connect on mount; clean up on unmount.
  useEffect(() => {
    connect();

    return () => {
      manuallyDisconnectedRef.current = true;
      clearReconnectTimer();

      if (abortControllerRef.current !== null) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, [connect, clearReconnectTimer]);

  return { events, isConnected, error, connect, disconnect };
}
