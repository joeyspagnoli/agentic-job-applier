// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Component test for the `TailoredResumeCell` delete-mutation error
 * display added in issue #41 item #2.
 *
 * Three branches of `TailoredResumeCell` share one `deleteMutation`:
 * FAILED, SUCCESS+TAILORED verdict, and SUCCESS served-base
 * (BASE / NO_IMPROVEMENT / PAGE_FIT_FAILED). Each branch must render
 * the error message under its delete button when `deleteTailorRun`
 * rejects so users see 404 / 500 failures instead of a silent no-op.
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
  getTailoredResumeUrl: vi.fn().mockReturnValue("about:blank"),
}));

import {
  deleteTailorRun,
  fetchAutomationSettings,
  fetchJobs,
  fetchJobsNow,
} from "@/lib/api/client";
import { JobsPage } from "@/pages/JobsPage";

const FAILING_DELETE_ERROR = "TAILOR_RUN_ALREADY_DELETED";

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
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TailoredResumeCell delete-mutation error display", () => {
  it("renders the delete error under the FAILED-branch button", async () => {
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

    const deleteButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByText(FAILING_DELETE_ERROR)).toBeInTheDocument();
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

  it("renders the delete error under the served-base button (BASE verdict)", async () => {
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

    const deleteButton = await screen.findByRole("button", {
      name: /Delete & retry/,
    });
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByText(FAILING_DELETE_ERROR)).toBeInTheDocument();
    });
  });

  it("does not render any delete error before the user clicks delete", async () => {
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

    expect(screen.queryByText(FAILING_DELETE_ERROR)).not.toBeInTheDocument();
  });
});
