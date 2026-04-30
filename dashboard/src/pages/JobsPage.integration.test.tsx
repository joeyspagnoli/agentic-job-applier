// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Integration test for the {@link JobsPage} "Fetch Jobs Now" button — the
 * Bug 3 fix that gives users visible feedback while the trigger request
 * is in flight and immediately after it succeeds.
 *
 * @remarks
 * Three states must be observable:
 *
 * 1. **Idle:** label reads "Fetch Jobs Now".
 * 2. **Pending:** label reads "Fetching" with three bouncing dots while
 *    the mutation is in flight; the button is `disabled`.
 * 3. **Just-triggered:** for {@link JUST_TRIGGERED_DURATION_MS} after the
 *    mutation resolves, the label reads "Triggered!"; after that window
 *    elapses, the label returns to "Fetch Jobs Now".
 *
 * The test stubs `fetchJobsNow` with a deferred promise so the pending
 * state is observable; `fetchJobs` is stubbed to keep the table render
 * inert.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { SystemLifecycleActionDto } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  fetchJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchJobsNow: vi.fn(),
  getTailoredResumeUrl: vi.fn().mockReturnValue("about:blank"),
}));

import { fetchJobsNow } from "@/lib/api/client";
import { JobsPage } from "@/pages/JobsPage";

/**
 * Window during which the "Triggered!" label remains on screen after
 * the fetch-now mutation resolves. Must stay in lockstep with the
 * `setTimeout(..., 2500)` inside `JobsPage.tsx`.
 */
const JUST_TRIGGERED_DURATION_MS = 2500;

/**
 * Build a `QueryClient` configured to fail fast in tests — no retries,
 * no refetch on mount, no background polling.
 */
function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

/**
 * Render `JobsPage` inside a fresh `QueryClient` and `MemoryRouter`.
 */
function renderJobsPage(queryClient: QueryClient): void {
  function Wrapper(): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <JobsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  render(<Wrapper />);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("JobsPage Fetch Jobs Now button feedback states (Bug 3)", () => {
  beforeEach(() => {
    vi.mocked(fetchJobsNow).mockReset();
  });

  it("transitions Idle → Fetching → Triggered! → Idle across the mutation lifecycle", async () => {
    // Arrange — a deferred fetchJobsNow we can release on demand.
    let releaseFetch: (value: SystemLifecycleActionDto) => void = () =>
      undefined;
    const fetchPromise = new Promise<SystemLifecycleActionDto>((resolve) => {
      releaseFetch = resolve;
    });
    vi.mocked(fetchJobsNow).mockReturnValue(fetchPromise);

    renderJobsPage(buildTestQueryClient());
    const user = userEvent.setup();

    // Assert (idle) — initial label is "Fetch Jobs Now" and the button
    // is enabled.
    const idleButton = await screen.findByRole("button", {
      name: "Fetch Jobs Now",
    });
    expect(idleButton).toBeEnabled();

    // Act — click; mutation is now pending.
    await user.click(idleButton);

    // Assert (pending) — label flips to "Fetching" with the three
    // bouncing-dot spans, and the button becomes disabled.
    const pendingButton = await screen.findByRole("button", {
      name: /Fetching/,
    });
    expect(pendingButton).toBeDisabled();
    expect(pendingButton.textContent).toContain("Fetching");
    const bouncingDots = pendingButton.querySelectorAll(
      "span.animate-bounce",
    );
    expect(bouncingDots).toHaveLength(3);

    // Act — release the deferred promise so onSuccess fires.
    releaseFetch({ status: "ok", message: "triggered" } as SystemLifecycleActionDto);

    // Assert (just-triggered) — label flips to "Triggered!" within the
    // 2.5 s confirmation window.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Triggered!" }),
      ).toBeInTheDocument();
    });

    // Assert (return-to-idle) — after the 2.5 s window elapses, the
    // label reverts to "Fetch Jobs Now".
    await waitFor(
      () => {
        expect(
          screen.getByRole("button", { name: "Fetch Jobs Now" }),
        ).toBeInTheDocument();
      },
      { timeout: JUST_TRIGGERED_DURATION_MS + 1500 },
    );
  }, 10000);
});
