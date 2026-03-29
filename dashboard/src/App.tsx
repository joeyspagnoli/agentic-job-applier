/**
 * @packageDocumentation
 *
 * Root application component — configures the React Router tree.
 *
 * @remarks
 * All five dashboard pages are rendered inside {@link AppLayout}, which
 * provides the shared sidebar, top bar, and settings panel. Add new routes
 * here as additional pages are implemented.
 */

import type { JSX } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { PlaceholderPage } from "@/pages/PlaceholderPage";

/**
 * Root React application component.
 *
 * @returns The application wrapped in a BrowserRouter with all routes defined.
 */
export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="jobs" element={<PlaceholderPage name="Jobs" />} />
          <Route path="human-review" element={<PlaceholderPage name="Human Review" />} />
          <Route path="failures" element={<PlaceholderPage name="Failures" />} />
          <Route path="cost-tracking" element={<PlaceholderPage name="Cost Tracking" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
