/**
 * @packageDocumentation
 *
 * Canonical sidebar navigation component for the AutoApply dashboard.
 *
 * @remarks
 * This is the single source of truth for the sidebar layout.
 * Do not duplicate or modify this component when adding new pages —
 * update the {@link NAV_ITEMS} array instead.
 */

import type { JSX } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { fetchBudget } from "@/lib/api/client";
import { formatUsd } from "@/lib/api/adapters";
import {
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_ON_SURFACE,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_HIGH,
  SIDEBAR_WIDTH_PX,
  Z_SIDEBAR,
} from "@/lib/design-tokens";

/** A single entry in the sidebar navigation list. */
interface NavItem {
  /** React Router path for this page. */
  readonly to: string;
  /** Human-readable label shown next to the icon. */
  readonly label: string;
  /** Material Symbols icon name (ligature text). */
  readonly icon: string;
  /**
   * Whether this route requires an exact path match for the active state.
   * Set `true` only for the root `/` route to prevent it from matching all paths.
   */
  readonly end: boolean;
}

/**
 * Ordered list of navigation destinations.
 *
 * @remarks
 * Rendered top-to-bottom in the sidebar. Order here defines the visual order.
 * Add new first-class pages here so navigation and routing stay centralized.
 */
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/jobs", label: "Jobs", icon: "work", end: false },
  { to: "/human-review", label: "Human Review", icon: "visibility", end: false },
  { to: "/failures", label: "Failures", icon: "error", end: false },
  { to: "/cost-tracking", label: "Cost Tracking", icon: "payments", end: false },
  { to: "/settings", label: "Settings", icon: "settings", end: false },
] as const satisfies readonly NavItem[];

/**
 * Fixed left-side navigation sidebar for the AutoApply dashboard.
 *
 * @remarks
 * Renders the AutoApply logo, six navigation links, and a read-only
 * monthly budget widget at the bottom. Active route highlighting is
 * handled automatically via React Router's {@link NavLink}.
 *
 * @returns The sidebar `<aside>` element.
 */
export function Sidebar(): JSX.Element {
  const { data: budgetData } = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
  });
  const spentText = formatUsd(budgetData?.spent_usd ?? 0);
  const limitText = formatUsd(budgetData?.monthly_budget_usd ?? 0);
  const usedPercent = Math.max(0, Math.min(100, Math.round(budgetData?.utilization_pct ?? 0)));

  return (
    <aside
      className="fixed left-0 top-0 h-screen bg-white border-r flex flex-col py-6"
      style={{
        width: SIDEBAR_WIDTH_PX,
        borderColor: `${COLOR_OUTLINE_VARIANT}4D`,
        zIndex: Z_SIDEBAR,
      }}
    >
      {/* Logo mark */}
      <div className="px-6 mb-8 flex items-center space-x-3">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center"
          style={{ backgroundColor: COLOR_PRIMARY }}
        >
          <span
            className="material-symbols-outlined text-white text-lg"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            bolt
          </span>
        </div>
        <span className="text-xl font-bold tracking-tight" style={{ color: COLOR_PRIMARY }}>
          AutoApply
        </span>
      </div>

      {/* Navigation links */}
      <nav className="flex-1 px-3 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              isActive
                ? "flex items-center space-x-3 px-4 py-2 rounded-lg border-l-4 transition-all"
                : "flex items-center space-x-3 px-4 py-2 rounded-lg transition-all"
            }
            style={({ isActive }) =>
              isActive
                ? {
                    backgroundColor: COLOR_PRIMARY_FIXED,
                    color: COLOR_PRIMARY,
                    borderLeftColor: COLOR_PRIMARY,
                  }
                : {
                    color: COLOR_ON_SURFACE_VARIANT,
                  }
            }
            onMouseEnter={(e) => {
              const target = e.currentTarget;
              if (!target.getAttribute("aria-current")) {
                target.style.backgroundColor = COLOR_SURFACE_CONTAINER_LOW;
              }
            }}
            onMouseLeave={(e) => {
              const target = e.currentTarget;
              if (!target.getAttribute("aria-current")) {
                target.style.backgroundColor = "";
              }
            }}
          >
            <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
            <span className="font-medium text-sm">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Read-only monthly budget widget */}
      <div className="px-4 mt-auto">
        <div
          className="rounded-xl p-4 shadow-sm border"
          style={{
            backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
            borderColor: `${COLOR_OUTLINE_VARIANT}33`,
          }}
        >
          <span
            className="text-[10px] font-bold tracking-widest uppercase"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Monthly Budget
          </span>
          <div className="flex justify-between items-baseline mt-1 mb-2">
            <span className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
              {spentText}
            </span>
            <span className="text-[10px]" style={{ color: COLOR_OUTLINE }}>
              / {limitText}
            </span>
          </div>
          <div
            className="w-full rounded-full h-1.5 overflow-hidden"
            style={{ backgroundColor: COLOR_SURFACE_CONTAINER_HIGH }}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${usedPercent}%`, backgroundColor: COLOR_PRIMARY }}
            />
          </div>
          <p className="text-[10px] mt-2 text-right font-medium" style={{ color: COLOR_OUTLINE }}>
            {usedPercent}% consumed
          </p>
        </div>
      </div>
    </aside>
  );
}
