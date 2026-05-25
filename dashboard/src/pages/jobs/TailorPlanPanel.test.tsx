// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Behavior tests for the "Why these edits" panel (Bug E, 2026-05-25).
 *
 * The panel must:
 *   1. Render a collapsed trigger by default so list rows stay light.
 *   2. Lazy-fetch and display the rationale-first JSON when expanded.
 *   3. Show the overall plan, per-bullet rationale, kept-unchanged
 *      notes, and the model attribution exactly as the API returns them.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { TailorRunPlanDto } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  fetchTailorRunPlan: vi.fn(),
}));

import { fetchTailorRunPlan } from "@/lib/api/client";
import { TailorPlanPanel } from "@/pages/jobs/TailorPlanPanel";

function renderPanel(runId: number): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper(): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <TailorPlanPanel runId={runId} />
      </QueryClientProvider>
    );
  }
  render(<Wrapper />);
}

function samplePlan(): TailorRunPlanDto {
  return {
    ok: true,
    plan: {
      model: "openai/gpt-5.4",
      saved_at: "2026-05-25T18:46:50Z",
      rewrite_plan: "Targeting bullets b1 and b2 for keyword alignment.",
      bullets_applied: 1,
      bullets_dropped: [],
      bullets: [
        {
          id: "b1",
          rationale: "Verb swap to mirror the JD's vocabulary.",
          action: "rewrite",
          new_text: "Classified anomalous traffic with 99.2% precision.",
        },
        {
          id: "b2",
          rationale: "Already matches the JD; left verbatim.",
          action: "keep",
          new_text: "",
        },
      ],
      kept_unchanged: [
        {
          id: "b3",
          reason: "Outside the section the JD emphasizes.",
        },
      ],
    },
  };
}

beforeEach(() => {
  vi.mocked(fetchTailorRunPlan).mockResolvedValue(samplePlan());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TailorPlanPanel", () => {
  it("renders only the trigger until the user clicks", () => {
    renderPanel(13);

    expect(
      screen.getByRole("button", { name: /Why these edits/i }),
    ).toBeInTheDocument();
    // The lazy-fetch contract: the API is NOT called until expansion.
    expect(fetchTailorRunPlan).not.toHaveBeenCalled();
  });

  it("fetches and renders the plan contents on expansion", async () => {
    renderPanel(13);

    await userEvent.click(
      screen.getByRole("button", { name: /Why these edits/i }),
    );

    await waitFor(() => {
      expect(fetchTailorRunPlan).toHaveBeenCalledWith(13);
    });

    expect(
      await screen.findByText(/Targeting bullets b1 and b2/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Verb swap to mirror the JD/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Classified anomalous traffic with 99.2% precision\./i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Outside the section the JD emphasizes\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/openai\/gpt-5\.4/i)).toBeInTheDocument();
  });

  it("surfaces an API failure without crashing", async () => {
    vi.mocked(fetchTailorRunPlan).mockRejectedValueOnce(
      new Error("HTTP 500: planner unreadable"),
    );

    renderPanel(13);
    await userEvent.click(
      screen.getByRole("button", { name: /Why these edits/i }),
    );

    expect(
      await screen.findByText(/Failed to load the planner artifact/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/planner unreadable/i)).toBeInTheDocument();
  });
});
