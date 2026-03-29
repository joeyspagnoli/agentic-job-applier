/**
 * @packageDocumentation
 *
 * Canonical top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Rendered above every page. Shows the current page title, auto-sync status,
 * manual sync action, and notification bell.
 */

import type { JSX } from "react";
import { useIsFetching } from "@tanstack/react-query";
import { useIsMutating } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
  COLOR_OUTLINE_VARIANT,
  Z_TOPBAR,
} from "@/lib/design-tokens";
import { shouldInvalidateOnSync } from "@/components/layout/topbar-sync";

const AUTO_SYNC_SECONDS = 30;

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
 * Sticky top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Displays the page title, explicit auto-sync status, manual sync trigger,
 * and notification bell.
 *
 * @param props - {@link TopBarProps}
 * @returns The sticky `<header>` element.
 */
export function TopBar({ title }: TopBarProps): JSX.Element {
  const queryClient = useQueryClient();
  const activeQueryCount = useIsFetching();
  const activeMutationCount = useIsMutating();

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
  const syncLabel = hasSyncError ? "SYNC ISSUES" : isSyncing ? "SYNCING NOW" : `AUTO SYNC (${AUTO_SYNC_SECONDS}s)`;
  const syncSubLabel = hasSyncError
    ? "One or more requests failed"
    : formatSyncTimestamp(lastSuccessfulSyncAt);
  const syncDotColor = hasSyncError ? "bg-red-500" : isSyncing ? "bg-green-500" : "bg-slate-400";

  function handleSyncNow(): void {
    void queryClient.invalidateQueries({
      predicate: (query) => {
        return shouldInvalidateOnSync(query.queryKey[0]);
      },
    });
  }

  return (
    <header
      className="sticky top-0 w-full bg-[#f8f9fa]/80 backdrop-blur-md flex justify-between items-center px-8 py-4 border-b"
      style={{ zIndex: Z_TOPBAR, borderColor: `${COLOR_OUTLINE_VARIANT}33` }}
    >
      <h1 className="font-bold text-2xl tracking-tight" style={{ color: COLOR_ON_SURFACE }}>
        {title}
      </h1>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 rounded-full border border-indigo-100">
          <span className={`w-2 h-2 rounded-full ${syncDotColor} ${isSyncing ? "animate-pulse" : ""}`} />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] font-bold text-indigo-700 tracking-wider">{syncLabel}</span>
            <span className="text-[10px] text-indigo-500">{syncSubLabel}</span>
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
        </div>
      </div>
    </header>
  );
}
