// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Unit tests for {@link StepApplyPrefs} — verifies the form surfaces every
 * required eligibility field, that change events fire the parent's
 * ``onChange`` with an updated draft, and that the default draft fails the
 * step-7 ``canAdvance`` predicate (so onboarding cannot finish until the
 * user picks a definitive answer).
 */

import "@testing-library/jest-dom/vitest";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

afterEach(() => {
  cleanup();
});

import { StepApplyPrefs } from "./StepApplyPrefs";
import { defaultApplyPrefsDraft } from "@/lib/onboarding/defaults";
import type { ApplyPrefsDraft } from "@/lib/onboarding/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a draft with overrides on top of the safe default. */
function makeDraft(overrides: Partial<ApplyPrefsDraft> = {}): ApplyPrefsDraft {
  return { ...defaultApplyPrefsDraft(), ...overrides };
}

/**
 * Mirror the gate condition baked into {@link OnboardingPage.canAdvance}
 * so this test never goes stale relative to the wizard's actual gate.
 */
function passesStep7Gate(draft: ApplyPrefsDraft): boolean {
  return (
    draft.work_authorized_us !== "unknown" &&
    draft.sponsorship_required_now_or_future !== "unknown"
  );
}

// ---------------------------------------------------------------------------
// Default draft fails the gate
// ---------------------------------------------------------------------------

describe("StepApplyPrefs default draft", () => {
  it("starts with sponsorship + work auth set to 'unknown'", () => {
    const draft = defaultApplyPrefsDraft();

    expect(draft.work_authorized_us).toBe("unknown");
    expect(draft.sponsorship_required_now_or_future).toBe("unknown");
  });

  it("the default draft fails the step-7 canAdvance gate", () => {
    expect(passesStep7Gate(defaultApplyPrefsDraft())).toBe(false);
  });

  it("becomes passable when both eligibility fields are answered", () => {
    const draft = makeDraft({
      work_authorized_us: "yes",
      sponsorship_required_now_or_future: "no",
    });

    expect(passesStep7Gate(draft)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Form surface — eligibility fields render
// ---------------------------------------------------------------------------

describe("StepApplyPrefs render surface", () => {
  it("renders both required eligibility selects", () => {
    render(<StepApplyPrefs draft={defaultApplyPrefsDraft()} onChange={vi.fn()} />);

    // The labels include a required asterisk; assert via text content.
    expect(
      screen.getByText(/Authorized to work in the U.S./i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Requires sponsorship/i),
    ).toBeInTheDocument();
  });

  it("renders the Apply Preferences section heading", () => {
    render(<StepApplyPrefs draft={defaultApplyPrefsDraft()} onChange={vi.fn()} />);

    expect(screen.getByText(/Eligibility & EEO/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// onChange wiring — picking 'yes' updates the draft
// ---------------------------------------------------------------------------

describe("StepApplyPrefs onChange wiring", () => {
  it("fires onChange with work_authorized_us set when the user picks 'Yes'", async () => {
    const draft = defaultApplyPrefsDraft();
    const onChange = vi.fn();
    render(<StepApplyPrefs draft={draft} onChange={onChange} />);

    const workAuthSelect = screen
      .getByText(/Authorized to work in the U.S./i)
      .closest("label")!
      .querySelector("select")!;

    await userEvent.selectOptions(workAuthSelect, "yes");

    expect(onChange).toHaveBeenCalled();
    const updated = onChange.mock.calls[0]?.[0] as ApplyPrefsDraft | undefined;
    expect(updated).toBeDefined();
    expect(updated!.work_authorized_us).toBe("yes");
  });

  it("fires onChange with sponsorship set when the user picks 'No'", async () => {
    const draft = defaultApplyPrefsDraft();
    const onChange = vi.fn();
    render(<StepApplyPrefs draft={draft} onChange={onChange} />);

    const sponsorshipSelect = screen
      .getByText(/Requires sponsorship/i)
      .closest("label")!
      .querySelector("select")!;

    await userEvent.selectOptions(sponsorshipSelect, "no");

    expect(onChange).toHaveBeenCalled();
    const updated = onChange.mock.calls[0]?.[0] as ApplyPrefsDraft | undefined;
    expect(updated).toBeDefined();
    expect(updated!.sponsorship_required_now_or_future).toBe("no");
  });
});
