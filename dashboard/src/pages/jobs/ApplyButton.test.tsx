// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Unit tests for {@link ApplyButton} — one test per UI state.
 *
 * @remarks
 * No network calls are made; all state is driven through props.
 */

import "@testing-library/jest-dom/vitest";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

afterEach(() => {
  cleanup();
});

import type { ApplyButtonProps } from "./ApplyButton";
import { ApplyButton } from "./ApplyButton";
import type { TailorRunSummaryModel } from "@/lib/api/adapters";
import type { ApplyRunDto } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Build a minimal TailorRunSummaryModel for tests. */
function makeTailorRun(overrides: Partial<TailorRunSummaryModel> = {}): TailorRunSummaryModel {
  return {
    id: 5,
    status: "SUCCESS",
    verdict: "TAILORED",
    pageCount: 1,
    error: null,
    pdfUrl: null,
    reviewReason: null,
    ...overrides,
  };
}

/** Build a minimal ApplyRunDto for tests. */
function makeApplyRun(overrides: Partial<ApplyRunDto> = {}): ApplyRunDto {
  return {
    id: 10,
    job_hash: "abc123",
    status: "PENDING",
    outcome: null,
    ats_platform: null,
    completed_at: null,
    screenshot_path: null,
    error: null,
    ...overrides,
  };
}

/** Render {@link ApplyButton} with sensible defaults for unspecified props. */
function renderButton(overrides: Partial<ApplyButtonProps> = {}): void {
  const props: ApplyButtonProps = {
    jobHash: "abc123",
    tailorRun: null,
    applyRun: null,
    onApply: vi.fn(),
    onTailorThenApply: vi.fn(),
    ...overrides,
  };
  render(<ApplyButton {...props} />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ApplyButton", () => {
  describe("state 1 — idle (no tailor run, no apply run)", () => {
    it("renders an Apply button", () => {
      renderButton({ tailorRun: null, applyRun: null });

      expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
    });

    it("fires onTailorThenApply when clicked in idle state", async () => {
      const onTailorThenApply = vi.fn();

      renderButton({ tailorRun: null, applyRun: null, onTailorThenApply });

      await userEvent.click(screen.getByRole("button", { name: "Apply" }));

      expect(onTailorThenApply).toHaveBeenCalledOnce();
    });
  });

  describe("state 2 — waiting on tailor run", () => {
    it("renders 'Waiting on tailor run #5…' when tailor is RUNNING", () => {
      renderButton({ tailorRun: makeTailorRun({ id: 5, status: "RUNNING" }) });

      expect(
        screen.getByRole("button", { name: "Waiting on tailor run #5…" }),
      ).toBeInTheDocument();
    });

    it("is disabled while tailor is RUNNING", () => {
      renderButton({ tailorRun: makeTailorRun({ id: 5, status: "RUNNING" }) });

      expect(screen.getByRole("button", { name: /Waiting on tailor run/ })).toBeDisabled();
    });

    it("is disabled while tailor is PENDING", () => {
      renderButton({ tailorRun: makeTailorRun({ id: 5, status: "PENDING" }) });

      expect(screen.getByRole("button", { name: /Waiting on tailor run/ })).toBeDisabled();
    });
  });

  describe("state 3 — apply in progress", () => {
    it("renders disabled 'Applying…' when apply run is RUNNING", () => {
      renderButton({
        tailorRun: null,
        applyRun: makeApplyRun({ status: "RUNNING" }),
      });

      const button = screen.getByRole("button", { name: "Applying…" });

      expect(button).toBeInTheDocument();
      expect(button).toBeDisabled();
    });

    it("renders disabled 'Applying…' when apply run is PENDING", () => {
      renderButton({
        tailorRun: null,
        applyRun: makeApplyRun({ status: "PENDING" }),
      });

      expect(screen.getByRole("button", { name: "Applying…" })).toBeDisabled();
    });
  });

  describe("state 4 — applied needs review (amber badge)", () => {
    it("renders amber 'Applied — needs review' badge", () => {
      renderButton({
        applyRun: makeApplyRun({ status: "SUCCESS", outcome: "NEEDS_REVIEW" }),
      });

      const badge = screen.getByText("Applied — needs review");

      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass("bg-amber-100");
      expect(badge).toHaveClass("text-amber-800");
    });
  });

  describe("state 5 — auto-applied (green badge)", () => {
    it("renders green 'Auto-applied' badge for SUBMITTED outcome", () => {
      renderButton({
        applyRun: makeApplyRun({ status: "SUCCESS", outcome: "SUBMITTED" }),
      });

      const badge = screen.getByText("Auto-applied");

      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass("bg-green-100");
      expect(badge).toHaveClass("text-green-800");
    });
  });

  describe("state 6 — apply failed (retry)", () => {
    it("renders 'Apply failed — retry' button when apply is FAILED", () => {
      renderButton({
        applyRun: makeApplyRun({ status: "FAILED" }),
      });

      expect(
        screen.getByRole("button", { name: "Apply failed — retry" }),
      ).toBeInTheDocument();
    });

    it("fires onApply when 'Apply failed — retry' is clicked", async () => {
      const onApply = vi.fn();

      renderButton({
        applyRun: makeApplyRun({ status: "FAILED" }),
        onApply,
      });

      await userEvent.click(screen.getByRole("button", { name: "Apply failed — retry" }));

      expect(onApply).toHaveBeenCalledOnce();
    });
  });
});
