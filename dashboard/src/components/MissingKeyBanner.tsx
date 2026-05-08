/**
 * @packageDocumentation
 *
 * Top-of-page warning banner shown when `OPENAI_API_KEY` is not configured
 * on the API process. Polls `/api/system/health` every 30 seconds (matching
 * the global TanStack Query refetch interval) and auto-dismisses when the
 * key becomes available.
 */

import type { JSX } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchSystemHealth, type SystemHealthDto } from "@/lib/api/client";
import {
  COLOR_ON_WARNING_CONTAINER,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";

/** Stable React Query cache key for the system health endpoint. */
const SYSTEM_HEALTH_QUERY_KEY = ["system-health"] as const;

/** Route + tab destination for the API Keys configuration screen. */
const API_KEYS_ROUTE = "/settings";

/**
 * Render a yellow warning banner when the backend reports `OPENAI_API_KEY`
 * is missing.
 *
 * @remarks
 * - Returns `null` while the first poll is in flight so we never flash a
 *   banner before learning the real state.
 * - Returns `null` when the key is configured (banner auto-dismisses on the
 *   next successful poll once the user saves it).
 * - Uses `role="status"` because the banner is informational and should not
 *   interrupt screen-reader users with an alert.
 *
 * @returns Yellow banner JSX when the key is missing, otherwise `null`.
 */
export function MissingKeyBanner(): JSX.Element | null {
  const { data, isLoading } = useQuery<SystemHealthDto>({
    queryKey: SYSTEM_HEALTH_QUERY_KEY,
    queryFn: fetchSystemHealth,
  });

  if (isLoading || data === undefined) {
    return null;
  }

  if (data.openai_key_configured) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="missing-key-banner"
      className="border-b px-6 py-3 text-sm font-medium"
      style={{
        backgroundColor: COLOR_WARNING_CONTAINER,
        borderColor: COLOR_WARNING,
        color: COLOR_ON_WARNING_CONTAINER,
      }}
    >
      <span>
        OpenAI API key not set — gate, tailor, and review are disabled. Set it in{" "}
        <Link
          to={API_KEYS_ROUTE}
          className="underline font-semibold"
          style={{ color: COLOR_ON_WARNING_CONTAINER }}
        >
          Settings &rarr; API Keys
        </Link>
        .
      </span>
    </div>
  );
}
