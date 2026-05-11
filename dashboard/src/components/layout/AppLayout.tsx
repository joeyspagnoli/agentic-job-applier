/**
 * @packageDocumentation
 *
 * Root layout shell that wraps every page in the AutoApply dashboard.
 *
 * @remarks
 * Renders the {@link Sidebar} and {@link TopBar} components around the
 * active page content delivered via React Router's `<Outlet />`.
 */

import type { JSX } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { COLOR_SURFACE, SIDEBAR_WIDTH_PX } from "@/lib/design-tokens";

/**
 * Maps each route path to the human-readable page title shown in the TopBar.
 *
 * @remarks
 * Keys must exactly match the route `path` values defined in `App.tsx`.
 * The root path `/` maps to "Dashboard".
 */
const PAGE_TITLES = {
  "/": "Dashboard",
  "/jobs": "Jobs",
  "/tailored-resumes": "Tailored Resumes",
  "/human-review": "Human Review",
  "/failures": "Failures",
  "/cost-tracking": "Cost Tracking",
  "/settings": "Settings",
} as const satisfies Record<string, string>;

/**
 * Resolves the page title for the current route.
 *
 * @param pathname - The current `location.pathname` value from React Router.
 * @returns The matching title string, or "Dashboard" as a safe fallback.
 */
function resolvePageTitle(pathname: string): string {
  return (PAGE_TITLES as Record<string, string>)[pathname] ?? "Dashboard";
}

/**
 * Top-level layout component shared by all dashboard pages.
 *
 * @remarks
 * Mount this as the element of a parent `<Route>` with child routes using
 * `<Outlet />` to render each page's content in the main area.
 *
 * @returns The full-page layout shell element.
 */
export function AppLayout(): JSX.Element {
  const location = useLocation();
  const pageTitle = resolvePageTitle(location.pathname);

  return (
    <div className="min-h-screen" style={{ backgroundColor: COLOR_SURFACE }}>
      <Sidebar />

      <div className="min-h-screen flex flex-col" style={{ marginLeft: SIDEBAR_WIDTH_PX }}>
        <TopBar title={pageTitle} />
        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
