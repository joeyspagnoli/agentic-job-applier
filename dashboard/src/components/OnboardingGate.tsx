/**
 * @packageDocumentation
 *
 * Gate component that redirects to onboarding when the user profile
 * is incomplete. Wraps the main app layout.
 */

import type { JSX, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { fetchOnboardingStatus } from "@/lib/api/client";

/** Props for the {@link OnboardingGate} wrapper. */
interface OnboardingGateProps {
  /** Child elements to render when onboarding is complete. */
  readonly children: ReactNode;
}

/**
 * Wraps the main app routes and redirects to `/onboarding` when the
 * user has not yet completed initial setup.
 *
 * @remarks
 * Renders nothing (blank screen) while the status check is loading.
 * Falls through to children if the endpoint errors (graceful degradation).
 *
 * @param props - {@link OnboardingGateProps}
 * @returns Children when onboarding is complete, or a redirect to `/onboarding`.
 */
export function OnboardingGate({ children }: OnboardingGateProps): JSX.Element {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: fetchOnboardingStatus,
    staleTime: 60_000,
    retry: 1,
  });

  if (isLoading) {
    return <div className="min-h-screen" />;
  }

  if (isError || data === undefined) {
    return <>{children}</>;
  }

  if (!data.is_complete) {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}
