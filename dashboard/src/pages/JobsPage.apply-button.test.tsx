// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Regression guard for Bug 1 — the Apply button on a row with a
 * SUCCESSful tailor run must POST `/api/jobs/{hash}/apply` and NEVER
 * re-POST `/tailor` (which would return 409 because the tailor run
 * already exists). Smoke-tested 2026-05-25; this test locks the
 * behavior so the bug cannot reappear from a future refactor.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type {
  AutomationSettingsDto,
  JobsItemDto,
  JobsResponseDto,
  TailorRunSummaryDto,
} from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  fetchJobs: vi.fn(),
  fetchJobsNow: vi.fn(),
  fetchAutomationSettings: vi.fn(),
  enqueueTailorRun: vi.fn(),
  deleteTailorRun: vi.fn(),
  retryTailorRun: vi.fn(),
  postApplyRun: vi.fn(),
  getTailoredResumeUrl: vi.fn().mockReturnValue("about:blank"),
  // ApplyRunConflictError class must remain a named export so JobsPage
  // can do `error instanceof ApplyRunConflictError`. We define a
  // minimal subclass here that satisfies that check.
  ApplyRunConflictError: class extends Error {
    public readonly runId: number;
    public readonly status: string;
    constructor(runId: number, status: string) {
      super("APPLY_RUN_IN_FLIGHT");
      this.runId = runId;
      this.status = status;
    }
  },
}));

import {
  enqueueTailorRun,
  fetchAutomationSettings,
  fetchJobs,
  fetchJobsNow,
  postApplyRun,
} from "@/lib/api/client";
import { JobsPage } from "@/pages/JobsPage";

const TEST_JOB_HASH = "abc123regressionhash";

function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

function renderJobsPage(): void {
  const queryClient = buildTestQueryClient();
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

function buildJobItem(tailorRun: TailorRunSummaryDto): JobsItemDto {
  return {
    id: 1,
    job_hash: TEST_JOB_HASH,
    company: "TestCo",
    position: "Eng",
    location: "Remote",
    pay: "—",
    work_type: "Remote",
    source: "TEST",
    status: "DISCOVERED",
    discovered: "2026-05-25T00:00:00Z",
    pipeline: [],
    gate_verdict: "PASS",
    gate_reasoning: "",
    tailored_resume: null,
    job_posting_url: "https://example.com/job",
    tailor_run: tailorRun,
  };
}

function buildJobsResponse(tailorRun: TailorRunSummaryDto): JobsResponseDto {
  return {
    ok: true,
    page: 1,
    page_size: 25,
    total_items: 1,
    total_pages: 1,
    items: [buildJobItem(tailorRun)],
  };
}

const AUTOMATION_OPT_IN: AutomationSettingsDto = {
  ok: true,
  tailor_mode: "opt_in",
};

beforeEach(() => {
  vi.mocked(fetchAutomationSettings).mockResolvedValue(AUTOMATION_OPT_IN);
  vi.mocked(fetchJobsNow).mockResolvedValue({
    ok: true,
    action: "fetch_jobs",
    status: "accepted",
    request_id: "test-req",
  });
  vi.mocked(postApplyRun).mockResolvedValue({
    ok: true,
    apply_run_id: 999,
    job_hash: TEST_JOB_HASH,
    status: "PENDING",
  });
  vi.mocked(enqueueTailorRun).mockResolvedValue({
    ok: true,
    tailor_run_id: 999,
    status: "PENDING",
    job_hash: TEST_JOB_HASH,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Bug 1 regression — ApplyButton must POST /apply, never re-POST /tailor", () => {
  it("posts /apply (not /tailor) when tailor SUCCESS picked TAILORED", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 42,
        status: "SUCCESS",
        verdict: "TAILORED",
        page_count: 1,
        error: null,
        pdf_url: "about:blank",
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const applyButton = await screen.findByRole("button", { name: "Apply" });
    await user.click(applyButton);

    await waitFor(() => {
      expect(vi.mocked(postApplyRun)).toHaveBeenCalledWith(TEST_JOB_HASH);
    });
    // The whole point of this regression — the tailor enqueue must NOT fire.
    expect(vi.mocked(enqueueTailorRun)).not.toHaveBeenCalled();
  });

  it("posts /apply (not /tailor) when tailor SUCCESS picked BASE", async () => {
    // Reviewer picked the base resume; tailor_run.status is still SUCCESS.
    // This is the exact case that wasted a smoke-test cycle on 2026-05-25
    // because the old button routed through the tailor enqueue.
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 43,
        status: "SUCCESS",
        verdict: "BASE",
        page_count: 1,
        error: null,
        pdf_url: "about:blank",
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const applyButton = await screen.findByRole("button", { name: "Apply" });
    await user.click(applyButton);

    await waitFor(() => {
      expect(vi.mocked(postApplyRun)).toHaveBeenCalledWith(TEST_JOB_HASH);
    });
    expect(vi.mocked(enqueueTailorRun)).not.toHaveBeenCalled();
  });

  it("opens the NotTailoredModal (no network calls yet) when no tailor exists", async () => {
    vi.mocked(fetchJobs).mockResolvedValue({
      ok: true,
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
      items: [
        {
          ...buildJobItem({
            id: 0,
            status: "SUCCESS",
            verdict: "TAILORED",
            page_count: 1,
            error: null,
            pdf_url: null,
          }),
          tailor_run: null,
        },
      ],
    });

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const applyButton = await screen.findByRole("button", { name: "Apply" });
    await user.click(applyButton);

    // Modal renders its primary CTA — verify it's now visible. Neither
    // API call should have fired on the click (the modal is the gate).
    await screen.findByRole("button", { name: /Yes, tailor/i });
    expect(vi.mocked(postApplyRun)).not.toHaveBeenCalled();
    expect(vi.mocked(enqueueTailorRun)).not.toHaveBeenCalled();
  });
});
