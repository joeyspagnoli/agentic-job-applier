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
import { FailuresPage } from "@/pages/FailuresPage";
import { HumanReviewPage } from "@/pages/HumanReviewPage";
import { CostTrackingPage } from "@/pages/CostTrackingPage";
import { JobsPage } from "@/pages/JobsPage";

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
          <Route path="jobs" element={<JobsPage />} />
          <Route path="human-review" element={<HumanReviewPage />} />
          <Route path="failures" element={<FailuresPage />} />
          <Route path="cost-tracking" element={<CostTrackingPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
