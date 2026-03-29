/**
 * @packageDocumentation
 *
 * Canonical top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Rendered above every page. Shows the current page title (passed as a prop),
 * a live-syncing status pill, notification bell, and an avatar dropdown
 * that surfaces the Settings panel and Log Out action.
 */

import type { JSX } from "react";
import { useState } from "react";
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

/** Props accepted by the {@link TopBar} component. */
interface TopBarProps {
  /** Human-readable page title displayed on the left side of the bar. */
  readonly title: string;
  /**
   * Optional callback invoked when the user clicks "Settings" in the avatar dropdown.
   * If omitted, the Settings option is rendered but clicking has no effect.
   */
  readonly onSettingsClick?: () => void;
}

/**
 * Sticky top navigation bar for the AutoApply dashboard.
 *
 * @remarks
 * Displays the page title, live-sync indicator, notification bell, and
 * an avatar dropdown with Settings and Log Out actions.
 * The avatar dropdown is toggled by clicking the user avatar area.
 *
 * @param props - {@link TopBarProps}
 * @returns The sticky `<header>` element.
 */
export function TopBar({ title, onSettingsClick }: TopBarProps): JSX.Element {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const queryClient = useQueryClient();
  const activeQueryCount = useIsFetching();
  const activeMutationCount = useIsMutating();
  const hasSyncError = queryClient
    .getQueryCache()
    .findAll()
    .some((query) => query.state.status === "error");

  const isSyncing = activeQueryCount > 0 || activeMutationCount > 0;
  const syncLabel = hasSyncError ? "SYNC ISSUES" : isSyncing ? "LIVE SYNCING" : "SYNC IDLE";
  const syncDotColor = hasSyncError ? "bg-red-500" : isSyncing ? "bg-green-500" : "bg-slate-400";

  function handleAvatarClick(): void {
    setIsDropdownOpen((previous) => !previous);
  }

  function handleSettingsClick(): void {
    setIsDropdownOpen(false);
    onSettingsClick?.();
  }

  function handleSyncNow(): void {
    void queryClient.invalidateQueries();
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
        {/* Live syncing status pill */}
        <div className="flex items-center gap-2 px-3 py-1 bg-indigo-50 rounded-full border border-indigo-100">
          <span className={`w-2 h-2 rounded-full ${syncDotColor} ${isSyncing ? "animate-pulse" : ""}`} />
          <span className="text-[10px] font-bold text-indigo-700 tracking-wider">{syncLabel}</span>
        </div>

        <div className="flex items-center gap-4" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {/* Manual sync button */}
          <button
            className="hover:transition-colors"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onClick={handleSyncNow}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = COLOR_PRIMARY;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
            }}
            aria-label="Sync now"
          >
            <span className="material-symbols-outlined">sync</span>
          </button>

          {/* Notification bell with unread indicator */}
          <button
            className="relative"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = COLOR_PRIMARY;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
            }}
            aria-label="Notifications"
          >
            <span className="material-symbols-outlined">notifications</span>
            <span
              className="absolute top-0 right-0 w-2 h-2 rounded-full border-2 border-white"
              style={{ backgroundColor: COLOR_PRIMARY }}
            />
          </button>

          <div
            className="h-8 w-px mx-2"
            style={{ backgroundColor: `${COLOR_OUTLINE_VARIANT}4D` }}
          />

          {/* Avatar and dropdown trigger */}
          <div className="relative">
            <button
              className="flex items-center gap-3 cursor-pointer"
              onClick={handleAvatarClick}
              aria-expanded={isDropdownOpen}
              aria-haspopup="menu"
              aria-label="User menu"
            >
              <div className="text-right">
                <p
                  className="text-xs font-bold leading-none mb-0.5"
                  style={{ color: COLOR_ON_SURFACE }}
                >
                  Alex Rivera
                </p>
                <p className="text-[10px]" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Pro Plan
                </p>
              </div>
              <div
                className="w-9 h-9 rounded-full border-2 flex items-center justify-center font-bold text-sm transition-all"
                style={{
                  backgroundColor: "#eef2ff",
                  borderColor: `${COLOR_PRIMARY}33`,
                  color: COLOR_PRIMARY,
                }}
              >
                AR
              </div>
            </button>

            {/* Dropdown menu */}
            {isDropdownOpen && (
              <div
                className="absolute right-0 mt-2 w-44 bg-white rounded-xl shadow-lg border py-1"
                role="menu"
                style={{ borderColor: `${COLOR_OUTLINE_VARIANT}4D` }}
              >
                <button
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left"
                  role="menuitem"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "#f3f4f5";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "";
                  }}
                  onClick={handleSettingsClick}
                >
                  <span className="material-symbols-outlined text-[18px]">settings</span>
                  Settings
                </button>
                <button
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left"
                  role="menuitem"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "#f3f4f5";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "";
                  }}
                >
                  <span className="material-symbols-outlined text-[18px]">logout</span>
                  Log Out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
