/**
 * @packageDocumentation
 *
 * Shared React Query client configuration for dashboard polling and caching.
 */

import { QueryClient } from "@tanstack/react-query";

const DEFAULT_REFETCH_INTERVAL_MS = 30_000;

/**
 * Singleton query client used by the dashboard app.
 *
 * @remarks
 * Polling is enabled globally so active views stay synchronized with backend
 * pipeline updates without manual refreshes.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchInterval: DEFAULT_REFETCH_INTERVAL_MS,
      refetchOnWindowFocus: true,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});
