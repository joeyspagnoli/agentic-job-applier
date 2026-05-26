// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Component test for the {@link TailoredResumeCell} NO_IMPROVEMENT
 * verdict display. The cell branches on the structured `reviewReason`
 * value pulled out of `review_runs.review_report_json` so users see why
 * the base resume was served instead of a generic explanation.
 *
 * Three reason values must each map to their dedicated copy:
 *
 * - `"tailor_bailed"` → "The tailor model declined to propose edits."
 * - `"all_edits_dropped"` →
 *   "The tailor's edits referenced unknown IDs and were dropped."
 * - `null` (or omitted) → "Reviewer thought the base resume was fine
 *   for this role." (the legitimate reviewer-decided case).
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen } from "@testing-library/react";
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
  fetchAutomationSettings,
  fetchJobs,
  fetchJobsNow,
} from "@/lib/api/client";
import { JobsPage } from "@/pages/JobsPage";

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

/**
 * Build a SUCCESS-status NO_IMPROVEMENT tailor-run snapshot with the
 * given `review_reason` so each test only has to set the field that
 * actually drives the branch under test.
 */
function buildNoImprovementRun(
  reviewReason: string | null,
): TailorRunSummaryDto {
  return {
    id: 99,
    status: "SUCCESS",
    verdict: "NO_IMPROVEMENT",
    page_count: 1,
    error: null,
    pdf_url: "about:blank",
    review_reason: reviewReason,
  };
}

/** Automation settings stub — opt_in so the action buttons render. */
const AUTOMATION_OPT_IN: AutomationSettingsDto = {
  ok: true,
  tailor_mode: "opt_in",
};

const TAILOR_BAILED_COPY = "The tailor model declined to propose edits.";
const ALL_EDITS_DROPPED_COPY =
  "The tailor's edits referenced unknown IDs and were dropped.";
const REVIEWER_CHOSE_BASE_COPY =
  "Reviewer thought the base resume was fine for this role.";

beforeEach(() => {
  vi.mocked(fetchAutomationSettings).mockResolvedValue(AUTOMATION_OPT_IN);
  vi.mocked(fetchJobsNow).mockResolvedValue({
    ok: true,
    action: "fetch_jobs",
    status: "accepted",
    request_id: "test-req",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TailoredResumeCell NO_IMPROVEMENT verdict copy", () => {
  it("renders the tailor-bailed copy when review_reason is 'tailor_bailed'", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse(buildNoImprovementRun("tailor_bailed")),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    expect(
      await screen.findByText(new RegExp(TAILOR_BAILED_COPY)),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(ALL_EDITS_DROPPED_COPY)),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(REVIEWER_CHOSE_BASE_COPY)),
    ).not.toBeInTheDocument();
  });

  it("renders the all-edits-dropped copy when review_reason is 'all_edits_dropped'", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse(buildNoImprovementRun("all_edits_dropped")),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    expect(
      await screen.findByText(new RegExp(ALL_EDITS_DROPPED_COPY)),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(TAILOR_BAILED_COPY)),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(REVIEWER_CHOSE_BASE_COPY)),
    ).not.toBeInTheDocument();
  });

  it("renders the reviewer-chose-base copy when review_reason is null", async () => {
    vi.mocked(fetchJobs).mockResolvedValue(
      buildJobsResponse(buildNoImprovementRun(null)),
    );

    renderJobsPage();
    const user = userEvent.setup();

    const row = await screen.findByText("TestCo");
    await user.click(row);

    expect(
      await screen.findByText(new RegExp(REVIEWER_CHOSE_BASE_COPY)),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(TAILOR_BAILED_COPY)),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(ALL_EDITS_DROPPED_COPY)),
    ).not.toBeInTheDocument();
  });
});
