// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Behavior tests for the StepEducation onboarding step (Bug D, 2026-05-25).
 */

import "@testing-library/jest-dom/vitest";

import type { JSX } from "react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { defaultEducationDraft } from "@/lib/onboarding/defaults";
import type { EducationEntry } from "@/lib/onboarding/types";
import { StepEducation } from "./StepEducation";

afterEach(() => {
  cleanup();
});

function ControlledStep(): JSX.Element {
  const [draft, setDraft] = useState<EducationEntry[]>(defaultEducationDraft());
  return <StepEducation draft={draft} onChange={setDraft} />;
}

describe("StepEducation", () => {
  it("starts empty and adds one row when the user clicks Add education", async () => {
    const user = userEvent.setup();
    render(<ControlledStep />);

    expect(screen.getByText(/No education entries yet\./i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Add education/i }));

    expect(
      screen.queryByText(/No education entries yet\./i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Entry 1")).toBeInTheDocument();
  });

  it("persists each typed field on the row including minors and the still-enrolled checkbox", async () => {
    const user = userEvent.setup();
    render(<ControlledStep />);

    await user.click(screen.getByRole("button", { name: /Add education/i }));

    await user.type(
      screen.getByPlaceholderText("University of Florida"),
      "MIT",
    );
    await user.type(
      screen.getByPlaceholderText("Bachelor of Science"),
      "B.S.",
    );
    await user.type(
      screen.getByPlaceholderText("Computer Science"),
      "EECS",
    );
    const minorsField = screen.getByLabelText(/Minors/i);
    // userEvent.type loses embedded newlines inside textareas in jsdom; fire
    // a synthetic change event so multi-line minors round-trip through state.
    fireEvent.change(minorsField, {
      target: { value: "Mathematics\nPhysics" },
    });
    await user.type(screen.getByPlaceholderText("3.8"), "4.0");
    await user.type(screen.getByPlaceholderText("2022-08"), "2023-09");
    await user.type(screen.getByPlaceholderText("2026-05"), "2027-06");

    const stillEnrolled = screen.getByLabelText(/Still enrolled/i);
    await user.click(stillEnrolled);

    expect(screen.getByPlaceholderText("University of Florida")).toHaveValue("MIT");
    expect(screen.getByPlaceholderText("Bachelor of Science")).toHaveValue("B.S.");
    expect(screen.getByPlaceholderText("Computer Science")).toHaveValue("EECS");
    expect(screen.getByPlaceholderText("3.8")).toHaveValue("4.0");
    expect(screen.getByPlaceholderText("2022-08")).toHaveValue("2023-09");
    // Checking still-enrolled also re-labels the end-date input.
    expect(
      screen.getByText(/Expected graduation \(YYYY-MM\)/i),
    ).toBeInTheDocument();
    expect(stillEnrolled).toBeChecked();
    expect(minorsField).toHaveValue("Mathematics\nPhysics");
  });

  it("removes a row when Remove is clicked", async () => {
    const user = userEvent.setup();
    render(<ControlledStep />);

    await user.click(screen.getByRole("button", { name: /Add education/i }));
    await user.click(screen.getByRole("button", { name: /Add education/i }));

    expect(screen.getByText("Entry 1")).toBeInTheDocument();
    expect(screen.getByText("Entry 2")).toBeInTheDocument();

    const removeButtons = screen.getAllByRole("button", { name: /Remove/i });
    await user.click(removeButtons[0]!);

    expect(screen.queryByText("Entry 2")).not.toBeInTheDocument();
    expect(screen.getByText("Entry 1")).toBeInTheDocument();
  });
});
