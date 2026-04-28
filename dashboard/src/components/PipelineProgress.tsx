/**
 * @packageDocumentation
 *
 * Visual progress indicator for the AutoApply pipeline SSE stream.
 *
 * @remarks
 * Consumes live events from {@link useSSE} and renders either a compact
 * pill (for TopBar embedding) or a full progress card (for dashboard pages).
 * Colours and spacing follow the project's pastel lavender design tokens.
 */

import type { JSX } from "react";
import { Activity, AlertTriangle, CheckCircle, Loader2, Pause } from "lucide-react";
import { useSSE } from "@/hooks/useSSE";
import type { PipelineEvent } from "@/hooks/useSSE";
import {
  COLOR_ERROR,
  COLOR_ERROR_CONTAINER,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SUCCESS,
  COLOR_SUCCESS_CONTAINER,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";

/** Props accepted by the {@link PipelineProgress} component. */
interface PipelineProgressProps {
  /**
   * When `true`, renders a minimal pill suitable for the TopBar.
   * When `false` (default), renders a full progress card.
   */
  readonly compact?: boolean;
}

/**
 * Derive a human-readable label from a raw stage identifier.
 *
 * @param stage - Machine-readable stage name from the SSE payload.
 * @returns Capitalised, space-separated display label.
 */
function formatStageLabel(stage: string): string {
  if (stage === "") {
    return "Initializing";
  }
  return stage
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Compact pill variant rendered inside the TopBar.
 *
 * @param latest - Most recent pipeline event, or `undefined` when idle.
 * @param isConnected - Whether the SSE stream is currently open.
 * @param totalErrors - Aggregate error count across all events.
 * @returns A small inline pill element.
 */
function CompactPill({
  latest,
  isConnected,
  totalErrors,
}: {
  readonly latest: PipelineEvent | undefined;
  readonly isConnected: boolean;
  readonly totalErrors: number;
}): JSX.Element {
  const isIdle = !isConnected || latest === undefined;
  const isComplete = latest !== undefined && latest.progress >= 1;

  // --- idle state ---
  if (isIdle) {
    return (
      <div
        className="flex items-center gap-1.5 rounded-full px-3 py-1.5"
        style={{ backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}
      >
        <Pause size={12} style={{ color: COLOR_OUTLINE }} />
        <span
          className="text-[10px] font-semibold tracking-wide"
          style={{ color: COLOR_OUTLINE }}
        >
          PIPELINE IDLE
        </span>
      </div>
    );
  }

  // --- error state ---
  if (totalErrors > 0) {
    return (
      <div
        className="flex items-center gap-1.5 rounded-full px-3 py-1.5"
        style={{ backgroundColor: COLOR_WARNING_CONTAINER }}
      >
        <AlertTriangle size={12} style={{ color: COLOR_WARNING }} />
        <span
          className="text-[10px] font-semibold tracking-wide"
          style={{ color: COLOR_WARNING }}
        >
          {totalErrors} ERROR{totalErrors > 1 ? "S" : ""}
        </span>
      </div>
    );
  }

  // --- complete state ---
  if (isComplete) {
    return (
      <div
        className="flex items-center gap-1.5 rounded-full px-3 py-1.5"
        style={{ backgroundColor: COLOR_SUCCESS_CONTAINER }}
      >
        <CheckCircle size={12} style={{ color: COLOR_SUCCESS }} />
        <span
          className="text-[10px] font-semibold tracking-wide"
          style={{ color: COLOR_SUCCESS }}
        >
          {latest.jobsFound} JOBS
        </span>
      </div>
    );
  }

  // --- active / in-progress state ---
  return (
    <div
      className="flex items-center gap-1.5 rounded-full px-3 py-1.5"
      style={{ backgroundColor: COLOR_PRIMARY_FIXED }}
    >
      <Loader2
        size={12}
        className="animate-spin"
        style={{ color: COLOR_PRIMARY }}
      />
      <span
        className="text-[10px] font-semibold tracking-wide"
        style={{ color: COLOR_PRIMARY }}
      >
        {Math.round(latest.progress * 100)}%
      </span>
    </div>
  );
}

/**
 * Full card variant rendered on the dashboard body.
 *
 * @param latest - Most recent pipeline event, or `undefined` when idle.
 * @param isConnected - Whether the SSE stream is currently open.
 * @param totalErrors - Aggregate error count across all events.
 * @param sseError - Hook-level connection error string, if any.
 * @returns A detailed progress card element.
 */
function FullCard({
  latest,
  isConnected,
  totalErrors,
  sseError,
}: {
  readonly latest: PipelineEvent | undefined;
  readonly isConnected: boolean;
  readonly totalErrors: number;
  readonly sseError: string | null;
}): JSX.Element {
  const isIdle = !isConnected || latest === undefined;
  const isComplete = latest !== undefined && latest.progress >= 1;
  const progressPercent = latest !== undefined ? Math.round(latest.progress * 100) : 0;

  return (
    <div
      className="rounded-2xl border p-5"
      style={{
        borderColor: `${COLOR_OUTLINE_VARIANT}40`,
        backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
      }}
    >
      {/* Header row */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} style={{ color: COLOR_PRIMARY }} />
          <span
            className="text-sm font-bold tracking-tight"
            style={{ color: COLOR_ON_SURFACE }}
          >
            Pipeline Progress
          </span>
        </div>

        {/* Status badge */}
        {isIdle ? (
          <span
            className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide"
            style={{
              backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
              color: COLOR_OUTLINE,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
            }}
          >
            IDLE
          </span>
        ) : isComplete ? (
          <span
            className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide"
            style={{
              backgroundColor: COLOR_SUCCESS_CONTAINER,
              color: COLOR_SUCCESS,
            }}
          >
            COMPLETE
          </span>
        ) : (
          <span
            className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide"
            style={{
              backgroundColor: COLOR_PRIMARY_FIXED,
              color: COLOR_PRIMARY,
            }}
          >
            RUNNING
          </span>
        )}
      </div>

      {/* Stage + Source */}
      {latest !== undefined && !isIdle ? (
        <div className="mb-3">
          <p
            className="text-sm font-semibold"
            style={{ color: COLOR_ON_SURFACE }}
          >
            {formatStageLabel(latest.stage)}
          </p>
          {latest.source !== "" ? (
            <p
              className="text-xs"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Source: {latest.source}
            </p>
          ) : null}
        </div>
      ) : (
        <p
          className="mb-3 text-sm"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
        >
          Pipeline idle — waiting for next run.
        </p>
      )}

      {/* Progress bar */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between">
          <span
            className="text-[11px] font-medium"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Progress
          </span>
          <span
            className="text-[11px] font-bold tabular-nums"
            style={{ color: COLOR_PRIMARY }}
          >
            {progressPercent}%
          </span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full"
          style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}40` }}
        >
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${String(progressPercent)}%`,
              backgroundColor: isComplete ? COLOR_SUCCESS : COLOR_PRIMARY,
              animation:
                !isIdle && !isComplete
                  ? "pipeline-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite"
                  : "none",
            }}
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span
            className="text-xs font-medium"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Jobs found:
          </span>
          <span
            className="text-xs font-bold tabular-nums"
            style={{ color: COLOR_ON_SURFACE }}
          >
            {latest?.jobsFound ?? 0}
          </span>
        </div>

        {totalErrors > 0 ? (
          <div
            className="flex items-center gap-1.5 rounded-full px-2 py-0.5"
            style={{ backgroundColor: COLOR_WARNING_CONTAINER }}
          >
            <AlertTriangle size={11} style={{ color: COLOR_WARNING }} />
            <span
              className="text-[11px] font-semibold"
              style={{ color: COLOR_WARNING }}
            >
              {totalErrors} error{totalErrors > 1 ? "s" : ""}
            </span>
          </div>
        ) : null}
      </div>

      {/* SSE connection error */}
      {sseError !== null ? (
        <div
          className="mt-3 rounded-lg px-3 py-2 text-xs"
          style={{
            backgroundColor: COLOR_ERROR_CONTAINER,
            color: COLOR_ERROR,
          }}
        >
          Connection error: {sseError}
        </div>
      ) : null}

      {/* Keyframe injection for pulse animation */}
      <style>{`
        @keyframes pipeline-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}

/**
 * Pipeline progress indicator driven by SSE events.
 *
 * @remarks
 * Renders a compact pill (for TopBar use) or a full card (for the
 * dashboard body) depending on the `compact` prop. Internally
 * subscribes to the `/api/pipeline/progress` SSE stream via
 * {@link useSSE}.
 *
 * @param props - {@link PipelineProgressProps}
 * @returns The progress UI element.
 *
 * @example
 * ```tsx
 * // In the TopBar:
 * <PipelineProgress compact />
 *
 * // On a dashboard page:
 * <PipelineProgress />
 * ```
 */
export function PipelineProgress({
  compact = false,
}: PipelineProgressProps): JSX.Element {
  const { events, isConnected, error: sseError } = useSSE();

  const latest: PipelineEvent | undefined = events.at(-1);

  const totalErrors = events.reduce(
    (count, event) => count + event.errors.length,
    0,
  );

  if (compact) {
    return (
      <CompactPill
        latest={latest}
        isConnected={isConnected}
        totalErrors={totalErrors}
      />
    );
  }

  return (
    <FullCard
      latest={latest}
      isConnected={isConnected}
      totalErrors={totalErrors}
      sseError={sseError}
    />
  );
}
