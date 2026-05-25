// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Behavior tests for Bug B — the Human Review page must:
 *   1. Render a small textarea per deferred question carrying the
 *      finisher's label (never the stale "Unresolved field" string).
 *   2. POST the typed values to /api/human-review/{id}/answers
 *      when the reviewer clicks Save answers.
 *   3. Pre-fill the textarea from `user_answers` returned by the API
 *      so a refresh does not lose work in progress.
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { HumanReviewResponseDto } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  fetchHumanReviewQueue: vi.fn(),
  completeHumanReview: vi.fn(),
  dismissHumanReview: vi.fn(),
  saveHumanReviewAnswers: vi.fn(),
}));

import {
  completeHumanReview,
  dismissHumanReview,
  fetchHumanReviewQueue,
  saveHumanReviewAnswers,
} from "@/lib/api/client";
import { HumanReviewPage } from "@/pages/HumanReviewPage";

function buildTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

function renderPage(): void {
  const queryClient = buildTestQueryClient();
  function Wrapper(): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <HumanReviewPage />
      </QueryClientProvider>
    );
  }
  render(<Wrapper />);
}

function buildQueueResponse(
  overrides: Partial<HumanReviewResponseDto["items"][number]> = {},
): HumanReviewResponseDto {
  return {
    ok: true,
    page: 1,
    page_size: 20,
    total_items: 1,
    total_pages: 1,
    items: [
      {
        id: 13,
        company_name: "Cloudflare",
        position: "ML Engineer Intern",
        status: "PENDING_REVIEW",
        confidence_pct: 42,
        applied_date: "2026-05-25T18:46:50",
        agent_diagnostic: "Apply outcome: NEEDS_REVIEW on greenhouse",
        job_posting_url: "https://example.com/jobs/test",
        resume_file_name: "resume.pdf",
        unresolved_fields: [
          {
            field_id: "e368",
            field_name: "Gender",
            ai_answer: "",
            reasoning: "EEO field; Tier 3.",
            answer_confidence: "medium",
          },
          {
            field_id: "e385",
            field_name: "Are you Hispanic/Latino?",
            ai_answer: "",
            reasoning: "EEO field; Tier 3.",
            answer_confidence: "medium",
          },
        ],
        user_answers: [],
        ...overrides,
      },
    ],
  };
}

beforeEach(() => {
  vi.mocked(fetchHumanReviewQueue).mockResolvedValue(buildQueueResponse());
  vi.mocked(completeHumanReview).mockResolvedValue({} as never);
  vi.mocked(dismissHumanReview).mockResolvedValue({} as never);
  vi.mocked(saveHumanReviewAnswers).mockResolvedValue({
    ok: true,
    user_answers: [],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HumanReviewPage textarea + save flow", () => {
  it("renders one textarea per deferred question with the finisher label", async () => {
    renderPage();

    const reviewButton = await screen.findByRole("button", { name: /Review/i });
    await userEvent.click(reviewButton);

    const genderTextarea = await screen.findByLabelText("Answer for Gender");
    const ethnicityTextarea = screen.getByLabelText(
      "Answer for Are you Hispanic/Latino?",
    );

    expect(genderTextarea).toBeInTheDocument();
    expect(ethnicityTextarea).toBeInTheDocument();

    // The stale "Unresolved field" placeholder must never be a textarea
    // label (the page header copy mentions "unresolved fields" in prose,
    // which is fine; what is NOT fine is showing it as a question name).
    expect(
      screen.queryByLabelText("Answer for Unresolved field"),
    ).not.toBeInTheDocument();
  });

  it("POSTs the typed answers when the reviewer clicks Save answers", async () => {
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: /Review/i }),
    );

    const genderTextarea = await screen.findByLabelText("Answer for Gender");
    await userEvent.type(genderTextarea, "Female");

    const saveButton = screen.getByRole("button", { name: /Save answers/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(saveHumanReviewAnswers).toHaveBeenCalledWith(13, [
        { field_id: "e368", answer: "Female" },
        { field_id: "e385", answer: "" },
      ]);
    });
  });

  it("prefills the textarea from server-returned user_answers", async () => {
    vi.mocked(fetchHumanReviewQueue).mockResolvedValueOnce(
      buildQueueResponse({
        user_answers: [
          { field_id: "e368", answer: "Prefer not to say" },
        ],
      }),
    );

    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: /Review/i }),
    );

    const genderTextarea = await screen.findByLabelText("Answer for Gender");
    expect(genderTextarea).toHaveValue("Prefer not to say");
  });
});
