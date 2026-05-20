// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Component test for the `TailoredResumeCell` mutation-error display.
 *
 * After issue #56 the three branches split across two mutations:
 *
 * * FAILED and SUCCESS served-base (BASE / NO_IMPROVEMENT /
 *   PAGE_FIT_FAILED) now call `retryTailorRun` — clicking "Delete &
 *   retry" must surface `retryMutation` errors under that button.
 * * SUCCESS+TAILORED still calls `deleteTailorRun` — "Delete tailored"
 *   must surface `deleteMutation` errors under it.
 *
 * Both contracts are locked here so a future refactor cannot
 * accidentally regress one branch onto the wrong mutation.
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
  getTailoredResumeUrl: vi.fn().mockReturnValue("about:blank"),
}));

import {
  deleteTailorRun,
  fetchAutomationSettings,
  fetchJobs,
  fetchJobsNow,
  retryTailorRun,
} from "@/lib/api/client";
import { JobsPage } from "@/pages/JobsPage";

const FAILING_DELETE_ERROR = "TAILOR_RUN_ALREADY_DELETED";
const FAILING_RETRY_ERROR = "BUDGET_EXCEEDED";

/** Build a `QueryClient` with retries off so failures surface immediately. */
function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

/** Render JobsPage inside a fresh client and router. */
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

/** Build a single jobs-table item with a tailor-run snapshot attached. */
function buildJobItem(tailorRun: TailorRunSummaryDto): JobsItemDto {
  return {
    id: 1,
    job_hash: "deadbeef",
    company: "TestCo",
    position: "Eng",
    location: "Remote",
    pay: "—",
    work_type: "Remote",
    source: "TEST",
    status: "DISCOVERED",
    discovered: "2026-05-14T00:00:00Z",
    pipeline: [],
    gate_verdict: "PASS",
    gate_reasoning: "",
    tailored_resume: null,
    job_posting_url: "https://example.com/job",
    tailor_run: tailorRun,
  };
}

/** Build a complete one-page jobs response wrapping a single row. */
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

/** Automation settings stub — opt_in so the action buttons render. */
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
  vi.mocked(deleteTailorRun).mockRejectedValue(new Error(FAILING_DELETE_ERROR));
  vi.mocked(retryTailorRun).mockRejectedValue(new Error(FAILING_RETRY_ERROR));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TailoredResumeCell mutation-error display", () => {
  it("renders the retry error under the FAILED-branch button", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 42,
        status: "FAILED",
        verdict: null,
        page_count: null,
        error: "boom",
        pdf_url: null,
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    const retryButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText(FAILING_RETRY_ERROR)).toBeInTheDocument();
    });
  });

  it("renders the delete error under the TAILORED-verdict button", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 43,
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

    const deleteButton = await screen.findByRole("button", {
      name: "Delete tailored",
    });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByText(FAILING_DELETE_ERROR)).toBeInTheDocument();
    });
  });

  it("renders the retry error under the served-base button (BASE verdict)", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 44,
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

    const retryButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText(FAILING_RETRY_ERROR)).toBeInTheDocument();
    });
  });

  it("does not render any mutation error before the user clicks", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 45,
        status: "FAILED",
        verdict: null,
        page_count: null,
        error: "boom",
        pdf_url: null,
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    await screen.findByRole("button", { name: /Delete & retry/ });

    expect(screen.queryByText(FAILING_RETRY_ERROR)).not.toBeInTheDocument();
    expect(screen.queryByText(FAILING_DELETE_ERROR)).not.toBeInTheDocument();
  });
});

describe("TailoredResumeCell mutation routing (issue #56)", () => {
  it("calls retryTailorRun (not deleteTailorRun) on the FAILED branch", async () => {
    vi.mocked(retryTailorRun).mockResolvedValue({
      ok: true,
      retry_via: "user",
      tailor_run_id: 999,
      status: "PENDING",
      job_hash: "deadbeef",
    });
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 142,
        status: "FAILED",
        verdict: null,
        page_count: null,
        error: "boom",
        pdf_url: null,
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);
    const retryButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(retryButton);

    await waitFor(() => {
      expect(vi.mocked(retryTailorRun)).toHaveBeenCalledWith(142);
    });
    expect(vi.mocked(deleteTailorRun)).not.toHaveBeenCalled();
  });

  it("calls retryTailorRun (not deleteTailorRun) on the served-base branch", async () => {
    vi.mocked(retryTailorRun).mockResolvedValue({
      ok: true,
      retry_via: "user",
      tailor_run_id: 1000,
      status: "PENDING",
      job_hash: "deadbeef",
    });
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 144,
        status: "SUCCESS",
        verdict: "NO_IMPROVEMENT",
        page_count: 1,
        error: null,
        pdf_url: "about:blank",
      }),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);
    const retryButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(retryButton);

    await waitFor(() => {
      expect(vi.mocked(retryTailorRun)).toHaveBeenCalledWith(144);
    });
    expect(vi.mocked(deleteTailorRun)).not.toHaveBeenCalled();
  });

  it("calls deleteTailorRun (not retryTailorRun) on the TAILORED branch", async () => {
    vi.mocked(deleteTailorRun).mockResolvedValue(undefined);
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse({
        id: 143,
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
    const deleteButton = await screen.findByRole("button", {
      name: "Delete tailored",
    });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(vi.mocked(deleteTailorRun)).toHaveBeenCalledWith(143);
    });
    expect(vi.mocked(retryTailorRun)).not.toHaveBeenCalled();
  });
});
