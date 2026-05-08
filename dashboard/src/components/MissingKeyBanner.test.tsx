// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Tests for {@link MissingKeyBanner}. Verifies the banner only renders when
 * the API health endpoint reports `openai_key_configured === false`, and
 * auto-dismisses once the polled value flips to `true`.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import type { SystemHealthDto } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  fetchSystemHealth: vi.fn(),
}));

import { fetchSystemHealth } from "@/lib/api/client";
import { MissingKeyBanner } from "@/components/MissingKeyBanner";

/**
 * Build a query client tuned for synchronous test behavior — no retry,
 * no background refetch, no window-focus polling.
 *
 * @returns Configured `QueryClient` for the test render tree.
 */
function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
}

/**
 * Render the banner inside a fresh `QueryClient` and `MemoryRouter`.
 *
 * @param queryClient - Test-scoped query client instance.
 */
function renderBanner(queryClient: QueryClient): void {
  function Wrapper(): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MissingKeyBanner />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  render(<Wrapper />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("MissingKeyBanner", () => {
  it("renders nothing while the first poll is in flight", () => {
    vi.mocked(fetchSystemHealth).mockImplementation(
      () => new Promise<SystemHealthDto>(() => {}),
    );

    renderBanner(buildTestQueryClient());

    expect(screen.queryByTestId("missing-key-banner")).not.toBeInTheDocument();
  });

  it("renders the warning banner when openai_key_configured is false", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue({
      ok: true,
      openai_key_configured: false,
    });

    renderBanner(buildTestQueryClient());

    const banner = await screen.findByTestId("missing-key-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveTextContent(/OpenAI API key not set/i);
    expect(banner).toHaveTextContent(/gate, tailor, and review are disabled/i);

    const link = screen.getByRole("link", { name: /Settings.*API Keys/i });
    expect(link).toHaveAttribute("href", "/settings");
  });

  it("renders nothing when openai_key_configured is true", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue({
      ok: true,
      openai_key_configured: true,
    });

    renderBanner(buildTestQueryClient());

    await waitFor(() => {
      expect(fetchSystemHealth).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("missing-key-banner")).not.toBeInTheDocument();
  });
});
