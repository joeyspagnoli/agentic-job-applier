/**
 * @packageDocumentation
 *
 * Canonical top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Rendered above every page. Shows the current page title, auto-sync status,
 * manual sync action, notification bell, and power actions.
 */

import type { JSX } from "react";
import { useEffect, useRef, useState } from "react";
import { useIsFetching } from "@tanstack/react-query";
import { useIsMutating } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY_FIXED,
  COLOR_PRIMARY,
  COLOR_OUTLINE_VARIANT,
  Z_TOPBAR,
} from "@/lib/design-tokens";
import { shouldInvalidateOnSync } from "@/components/layout/topbar-sync";
import { restartSystemStack, stopSystemStack } from "@/lib/api/client";

const AUTO_SYNC_SECONDS = 30;
const POWER_ACTION_STOP = "stop";
const POWER_ACTION_RESTART = "restart";

type PowerAction = typeof POWER_ACTION_STOP | typeof POWER_ACTION_RESTART;

/** Props accepted by the {@link TopBar} component. */
interface TopBarProps {
  /** Human-readable page title displayed on the left side of the bar. */
  readonly title: string;
}

/**
 * Convert sync timestamp to compact local-time text.
 *
 * @param updatedAt - Timestamp in milliseconds, or null when unavailable.
 * @returns Human-readable sync time text.
 */
function formatSyncTimestamp(updatedAt: number | null): string {
  if (updatedAt === null) {
    return "No successful refresh yet";
  }

  const dateValue = new Date(updatedAt);
  if (Number.isNaN(dateValue.valueOf())) {
    return "No successful refresh yet";
  }

  return `Last refresh ${dateValue.toLocaleString()}`;
}

/**
 * Convert one thrown mutation error into a user-facing message.
 *
 * @param error - Unknown thrown value from lifecycle action requests.
 * @returns Human-readable fallback-safe message.
 */
function formatPowerActionError(error: unknown): string {
  if (error instanceof Error && error.message.trim() !== "") {
    return error.message;
  }
  return "Action failed. Please try again.";
}

/**
 * Sticky top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Displays the page title, explicit auto-sync status, manual sync trigger,
 * notification bell, and lifecycle power actions.
 *
 * @param props - {@link TopBarProps}
 * @returns The sticky `<header>` element.
 */
export function TopBar({ title }: TopBarProps): JSX.Element {
  const queryClient = useQueryClient();
  const activeQueryCount = useIsFetching();
  const activeMutationCount = useIsMutating();
  const powerMenuContainerRef = useRef<HTMLDivElement | null>(null);
  const [isPowerModalOpen, setIsPowerModalOpen] = useState<boolean>(false);
  const [activePowerAction, setActivePowerAction] = useState<PowerAction | null>(null);
  const [powerActionError, setPowerActionError] = useState<string | null>(null);

  const allQueries = queryClient.getQueryCache().findAll();
  const hasSyncError = allQueries.some((query) => query.state.status === "error");
  const lastSuccessfulSyncAt = allQueries
    .filter((query) => query.state.status === "success")
    .reduce<number | null>((latestTimestamp, query) => {
      const candidateTimestamp = query.state.dataUpdatedAt;
      if (candidateTimestamp <= 0) {
        return latestTimestamp;
      }
      if (latestTimestamp === null || candidateTimestamp > latestTimestamp) {
        return candidateTimestamp;
      }
      return latestTimestamp;
    }, null);

  const isSyncing = activeQueryCount > 0 || activeMutationCount > 0;
  const syncLabel = hasSyncError
    ? "SYNC ISSUES"
    : isSyncing
      ? "SYNCING NOW"
      : `AUTO SYNC (${AUTO_SYNC_SECONDS}s)`;
  const syncSubLabel = hasSyncError
    ? "One or more requests failed"
    : formatSyncTimestamp(lastSuccessfulSyncAt);
  const syncDotColor = hasSyncError ? "bg-error" : isSyncing ? "bg-success" : "bg-outline";
  const isPowerActionPending = activePowerAction !== null;

  useEffect(() => {
    if (!isPowerModalOpen) {
      return;
    }

    /**
     * Close power menu when click happens outside the power action container.
     *
     * @param event - Global pointer event fired from the document.
     * @returns Nothing.
     */
    function handleDocumentPointerDown(event: PointerEvent): void {
      if (
        powerMenuContainerRef.current === null ||
        !(event.target instanceof Node) ||
        powerMenuContainerRef.current.contains(event.target)
      ) {
        return;
      }

      setPowerActionError(null);
      setIsPowerModalOpen(false);
    }

    document.addEventListener("pointerdown", handleDocumentPointerDown);
    return () => {
      document.removeEventListener("pointerdown", handleDocumentPointerDown);
    };
  }, [isPowerModalOpen]);

  function handleSyncNow(): void {
    void queryClient.invalidateQueries({
      predicate: (query) => {
        return shouldInvalidateOnSync(query.queryKey[0]);
      },
    });
  }

  async function handlePowerActionSelection(action: PowerAction): Promise<void> {
    setPowerActionError(null);
    setActivePowerAction(action);

    try {
      if (action === POWER_ACTION_STOP) {
        await stopSystemStack();
      } else {
        await restartSystemStack();
      }
      setIsPowerModalOpen(false);
    } catch (error: unknown) {
      setPowerActionError(formatPowerActionError(error));
    } finally {
      setActivePowerAction(null);
    }
  }

  return (
    <header
      className="sticky top-0 w-full bg-[#f8f9fa] shadow-none flex justify-between items-center px-8 py-4 border-b"
      style={{ zIndex: Z_TOPBAR, borderColor: `${COLOR_OUTLINE_VARIANT}33` }}
    >
      <h1 className="font-bold text-2xl tracking-tight" style={{ color: COLOR_ON_SURFACE }}>
        {title}
      </h1>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 px-3 py-2 bg-primary-fixed rounded-full border border-primary-fixed">
          <span
            className={`w-2 h-2 rounded-full ${syncDotColor} ${isSyncing ? "animate-pulse" : ""}`}
          />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] font-bold text-primary tracking-wider">{syncLabel}</span>
            <span className="text-[10px] text-primary/70">{syncSubLabel}</span>
          </div>
        </div>

        <div className="flex items-center gap-4" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <button
            className="hover:transition-colors"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onClick={handleSyncNow}
            onMouseEnter={(event) => {
              event.currentTarget.style.color = COLOR_PRIMARY;
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
            }}
            aria-label="Sync now"
          >
            <span className="material-symbols-outlined">sync</span>
          </button>

          <button
            className="relative"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onMouseEnter={(event) => {
              event.currentTarget.style.color = COLOR_PRIMARY;
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
            }}
            aria-label="Notifications"
          >
            <span className="material-symbols-outlined">notifications</span>
            <span
              className="absolute top-0 right-0 w-2 h-2 rounded-full border-2 border-white"
              style={{ backgroundColor: COLOR_PRIMARY }}
            />
          </button>

          <div className="relative" ref={powerMenuContainerRef}>
            <button
              className="hover:transition-colors"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
              onClick={() => {
                setPowerActionError(null);
                setIsPowerModalOpen((previousValue) => !previousValue);
              }}
              onMouseEnter={(event) => {
                event.currentTarget.style.color = COLOR_PRIMARY;
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
              }}
              aria-label="Power actions"
              aria-haspopup="menu"
              aria-expanded={isPowerModalOpen}
            >
              <span className="material-symbols-outlined">power_settings_new</span>
            </button>

            {isPowerModalOpen ? (
              <div
                className="absolute right-0 top-full mt-2 min-w-[220px] overflow-hidden rounded-xl border bg-white"
                style={{
                  borderColor: `${COLOR_OUTLINE_VARIANT}66`,
                  zIndex: Z_TOPBAR + 1,
                }}
                role="menu"
                aria-label="System power actions"
              >
                <button
                  className="w-full px-4 py-2.5 text-left text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                  style={{
                    color: COLOR_ERROR,
                    backgroundColor:
                      activePowerAction === POWER_ACTION_STOP ? `${COLOR_ERROR}14` : "#ffffff",
                  }}
                  disabled={isPowerActionPending}
                  onClick={() => {
                    void handlePowerActionSelection(POWER_ACTION_STOP);
                  }}
                  role="menuitem"
                >
                  {activePowerAction === POWER_ACTION_STOP ? "Shutting down..." : "Shut Down"}
                </button>

                <button
                  className="w-full border-t px-4 py-2.5 text-left text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                  style={{
                    borderColor: `${COLOR_OUTLINE_VARIANT}66`,
                    color: COLOR_ON_SURFACE,
                    backgroundColor:
                      activePowerAction === POWER_ACTION_RESTART
                        ? `${COLOR_PRIMARY_FIXED}88`
                        : "#ffffff",
                  }}
                  disabled={isPowerActionPending}
                  onClick={() => {
                    void handlePowerActionSelection(POWER_ACTION_RESTART);
                  }}
                  role="menuitem"
                >
                  {activePowerAction === POWER_ACTION_RESTART ? "Restarting..." : "Restart"}
                </button>

                {powerActionError ? (
                  <p
                    className="border-t px-4 py-2 text-xs"
                    style={{
                      borderColor: `${COLOR_OUTLINE_VARIANT}66`,
                      color: COLOR_ERROR,
                    }}
                  >
                    {powerActionError}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
