/**
 * @packageDocumentation
 *
 * Canonical top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Rendered above every page. Shows three chips: the auto-sync status,
 * the global autonomous toggle, and the host Chrome reachability chip.
 * The chip layout accommodates single-container Docker deployment without
 * requiring multi-service orchestration.
 */

import type { JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  useIsFetching,
  useIsMutating,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SURFACE,
  Z_TOPBAR,
} from "@/lib/design-tokens";
import { fetchChromeStatus } from "@/lib/api/client";
import type { ChromeStatusDto, ChromeStatusOsHint } from "@/lib/api/types";

const AUTO_SYNC_SECONDS = 30;
const CHROME_POLL_MS = 30_000;

const COLOR_SUCCESS_DOT = "#3DD68C";

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
 * Detect the current host platform for the Chrome launch command hint.
 *
 * @returns One of `"mac" | "linux" | "windows"`, with mac as the default.
 */
function detectOsHint(): ChromeStatusOsHint {
  if (typeof window === "undefined") {
    return "mac";
  }
  const platform = window.navigator.platform.toLowerCase();
  if (platform.includes("win")) {
    return "windows";
  }
  if (platform.includes("linux")) {
    return "linux";
  }
  return "mac";
}

/**
 * Sticky top navigation bar for the AutoApply dashboard.
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
    .reduce<number | null>((latest, query) => {
      const candidate = query.state.dataUpdatedAt;
      if (candidate <= 0) {
        return latest;
      }
      if (latest === null || candidate > latest) {
        return candidate;
      }
      return latest;
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
  const syncDotClass = hasSyncError ? "bg-error" : isSyncing ? "bg-success" : "bg-outline";

  return (
    <header
      className="sticky top-0 w-full shadow-none flex justify-between items-center px-8 py-4 border-b"
      style={{
        zIndex: Z_TOPBAR,
        borderColor: `${COLOR_OUTLINE_VARIANT}30`,
        backgroundColor: COLOR_SURFACE,
      }}
    >
      <h1 className="text-fluid-xl font-bold tracking-tight" style={{ color: COLOR_ON_SURFACE }}>
        {title}
      </h1>

      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-xl"
          style={{ backgroundColor: COLOR_PRIMARY_FIXED }}
        >
          <span
            className={`w-2 h-2 rounded-full ${syncDotClass} ${isSyncing ? "animate-pulse" : ""}`}
          />
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] font-bold tracking-wider" style={{ color: COLOR_PRIMARY }}>
              {syncLabel}
            </span>
            <span className="text-[10px]" style={{ color: `${COLOR_PRIMARY}99` }}>
              {syncSubLabel}
            </span>
          </div>
        </div>

        <ChromeStatusChip />
      </div>
    </header>
  );
}

/**
 * Chrome reachability chip rendered in the top bar.
 *
 * @remarks
 * Polls `/api/status/chrome` every {@link CHROME_POLL_MS} milliseconds and
 * shows green when reachable, red when not. Clicking opens a popover with
 * the OS-appropriate copy-paste command for starting host Chrome with the
 * `--remote-debugging-port=9222` flag.
 *
 * @returns The Chrome status chip element.
 */
function ChromeStatusChip(): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isPopoverOpen, setIsPopoverOpen] = useState<boolean>(false);
  const [didCopy, setDidCopy] = useState<boolean>(false);

  const osHint = useMemo(() => detectOsHint(), []);

  const chromeQuery = useQuery<ChromeStatusDto>({
    queryKey: ["status", "chrome", osHint],
    queryFn: () => fetchChromeStatus(osHint),
    refetchInterval: CHROME_POLL_MS,
  });

  const reachable = chromeQuery.data?.reachable === true;
  const commandHint = chromeQuery.data?.command_hint ?? "";

  useEffect(() => {
    if (!isPopoverOpen) {
      return;
    }
    function handlePointerDown(event: PointerEvent): void {
      if (
        containerRef.current === null ||
        !(event.target instanceof Node) ||
        containerRef.current.contains(event.target)
      ) {
        return;
      }
      setIsPopoverOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [isPopoverOpen]);

  function handleCopy(): void {
    if (commandHint === "") {
      return;
    }
    void navigator.clipboard.writeText(commandHint).then(() => {
      setDidCopy(true);
      window.setTimeout(() => {
        setDidCopy(false);
      }, 1500);
    });
  }

  const dotColor = reachable ? COLOR_SUCCESS_DOT : COLOR_ERROR;
  const labelText = reachable ? "Chrome ready" : "Chrome offline";

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="flex items-center gap-2 px-3 py-2 rounded-xl border"
        style={{
          borderColor: `${COLOR_OUTLINE_VARIANT}50`,
          backgroundColor: COLOR_SURFACE,
        }}
        onClick={() => {
          setIsPopoverOpen((previousValue) => !previousValue);
        }}
        aria-label="Show Chrome launch command"
        aria-expanded={isPopoverOpen}
      >
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: dotColor }} />
        <span className="text-[10px] font-bold tracking-wider" style={{ color: COLOR_ON_SURFACE }}>
          {labelText}
        </span>
      </button>

      {isPopoverOpen ? (
        <div
          className="absolute right-0 top-full mt-2 min-w-[320px] overflow-hidden rounded-xl border ambient-shadow p-3"
          style={{
            borderColor: `${COLOR_OUTLINE_VARIANT}40`,
            backgroundColor: COLOR_SURFACE,
            zIndex: Z_TOPBAR + 1,
          }}
          role="dialog"
          aria-label="Host Chrome launch instructions"
        >
          <p className="text-xs mb-2" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            {reachable
              ? "Host Chrome is reachable. Apply loop will use it for the next claim."
              : "Apply loop is paused until host Chrome is reachable. Run this on your host:"}
          </p>
          <pre
            className="text-[11px] p-2 rounded-md overflow-x-auto"
            style={{
              backgroundColor: COLOR_PRIMARY_FIXED,
              color: COLOR_ON_SURFACE,
            }}
          >
            {commandHint || "Loading…"}
          </pre>
          <div className="flex justify-end mt-2">
            <button
              type="button"
              className="text-xs px-2 py-1 rounded-md font-semibold"
              style={{
                color: COLOR_PRIMARY,
                backgroundColor: `${COLOR_PRIMARY_FIXED}cc`,
              }}
              onClick={handleCopy}
              disabled={commandHint === ""}
            >
              {didCopy ? "Copied!" : "Copy command"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
