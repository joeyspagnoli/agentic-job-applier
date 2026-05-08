/**
 * @packageDocumentation
 *
 * Root application component — configures the React Router tree.
 *
 * @remarks
 * All dashboard pages are rendered inside {@link AppLayout}, which provides
 * the shared sidebar and top bar shell. Add new routes here as additional
 * pages are implemented.
 */

import type { JSX } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { CommandBar, useCommandBar } from "@/components/CommandBar";
import { MissingKeyBanner } from "@/components/MissingKeyBanner";
import { OnboardingGate } from "@/components/OnboardingGate";
import { DashboardPage } from "@/pages/DashboardPage";
import { FailuresPage } from "@/pages/FailuresPage";
import { HumanReviewPage } from "@/pages/HumanReviewPage";
import { CostTrackingPage } from "@/pages/CostTrackingPage";
import { JobsPage } from "@/pages/JobsPage";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { SettingsPage } from "@/pages/SettingsPage";

/**
 * Root React application component.
 *
 * @returns The application wrapped in a BrowserRouter with all routes defined.
 */
export default function App(): JSX.Element {
  const { open, setOpen } = useCommandBar();

  return (
    <BrowserRouter>
      <CommandBar open={open} onClose={() => setOpen(false)} />
      <MissingKeyBanner />
      <Routes>
        <Route path="onboarding" element={<OnboardingPage />} />
        <Route
          element={
            <OnboardingGate>
              <AppLayout />
            </OnboardingGate>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="human-review" element={<HumanReviewPage />} />
          <Route path="failures" element={<FailuresPage />} />
          <Route path="cost-tracking" element={<CostTrackingPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
