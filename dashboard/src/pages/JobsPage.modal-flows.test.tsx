// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Regression guards for the NotTailoredModal flows shipped in the
 * post-#59 apply-UX fix:
 *
 *   1. "No, skip tailoring" → POST /apply with `{ resumeMode: "base" }`,
 *      no follow-up POST /tailor.
 *   2. "Yes, tailor my resume" → POST /tailor with `{ applyAfter: true }`,
 *      no client-side chained POST /apply (the backend does it).
 *   3. A 409 `RUN_ALREADY_EXISTS` from the standalone "Tailor resume"
 *      button is swallowed silently so the user does not see a red
 *      error banner under a button that already had its job done.
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

const TEST_JOB_HASH = "abc123modalflowhash";

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

function buildJobItem(tailorRun: TailorRunSummaryDto | null): JobsItemDto {
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

function buildJobsResponseWithoutTailor(): JobsResponseDto {
  return {
    ok: true,
    page: 1,
    page_size: 25,
    total_items: 1,
    total_pages: 1,
    items: [buildJobItem(null)],
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

describe("NotTailoredModal flows", () => {
  it("posts /apply with resumeMode=base when user clicks 'No, skip tailoring'", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(buildJobsResponseWithoutTailor());

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const applyButton = await screen.findByRole("button", { name: "Apply" });
    await user.click(applyButton);

    const skipButton = await screen.findByRole("button", {
      name: /No, skip tailoring/i,
    });
    await user.click(skipButton);

    await waitFor(() => {
      expect(vi.mocked(postApplyRun)).toHaveBeenCalledWith(TEST_JOB_HASH, {
        resumeMode: "base",
      });
    });
    expect(vi.mocked(enqueueTailorRun)).not.toHaveBeenCalled();
  });

  it("posts /tailor with applyAfter=true when user clicks 'Yes, tailor my resume'", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(buildJobsResponseWithoutTailor());

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const applyButton = await screen.findByRole("button", { name: "Apply" });
    await user.click(applyButton);

    const tailorButton = await screen.findByRole("button", {
      name: /Yes, tailor my resume/i,
    });
    await user.click(tailorButton);

    await waitFor(() => {
      expect(vi.mocked(enqueueTailorRun)).toHaveBeenCalledWith(TEST_JOB_HASH, {
        applyAfter: true,
      });
    });
    // The whole point: the dashboard does NOT chain a /apply call —
    // the backend BackgroundTask enqueues apply itself after success.
    expect(vi.mocked(postApplyRun)).not.toHaveBeenCalled();
  });

  it("swallows RUN_ALREADY_EXISTS from the standalone Tailor button", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(buildJobsResponseWithoutTailor());
    const error = Object.assign(new Error("already exists"), {
      code: "RUN_ALREADY_EXISTS",
      details: {},
    });
    vi.mocked(enqueueTailorRun).mockRejectedValueOnce(error);

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const standaloneTailorButton = await screen.findByRole("button", {
      name: /Tailor resume/i,
    });
    await user.click(standaloneTailorButton);

    await waitFor(() => {
      expect(vi.mocked(enqueueTailorRun)).toHaveBeenCalled();
    });

    // No red error banner: the rejected text should not be rendered.
    expect(screen.queryByText(/already exists/i)).not.toBeInTheDocument();
  });
});
