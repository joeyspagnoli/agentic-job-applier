// @vitest-environment jsdom
/**
 * @packageDocumentation
 *
 * Unit tests for {@link NotTailoredModal} — verifies CTA callbacks,
 * backdrop close, and Escape key close behavior.
 */

import "@testing-library/jest-dom/vitest";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

afterEach(() => {
  cleanup();
});

import { NotTailoredModal } from "./NotTailoredModal";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Render the modal with all callbacks as vi.fn() stubs.
 *
 * @param open - Whether the modal should be open.
 * @returns The three callback stubs for assertion.
 */
function renderModal(open: boolean = true) {
  const onClose = vi.fn();
  const onApply = vi.fn();
  const onTailorThenApply = vi.fn();

  render(
    <NotTailoredModal
      open={open}
      onClose={onClose}
      onApply={onApply}
      onTailorThenApply={onTailorThenApply}
    />,
  );

  return { onClose, onApply, onTailorThenApply };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NotTailoredModal", () => {
  describe("when open", () => {
    it("renders the dialog with both CTA buttons visible", () => {
      renderModal(true);

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Yes, tailor my resume" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "No, skip tailoring" })).toBeInTheDocument();
    });

    it("fires onTailorThenApply when primary CTA is clicked", async () => {
      const { onTailorThenApply, onApply } = renderModal(true);

      await userEvent.click(screen.getByRole("button", { name: "Yes, tailor my resume" }));

      expect(onTailorThenApply).toHaveBeenCalledOnce();
      expect(onApply).not.toHaveBeenCalled();
    });

    it("fires onApply when secondary CTA is clicked", async () => {
      const { onApply, onTailorThenApply } = renderModal(true);

      await userEvent.click(screen.getByRole("button", { name: "No, skip tailoring" }));

      expect(onApply).toHaveBeenCalledOnce();
      expect(onTailorThenApply).not.toHaveBeenCalled();
    });

    it("fires onClose when Escape key is pressed", async () => {
      const { onClose } = renderModal(true);

      await userEvent.keyboard("{Escape}");

      expect(onClose).toHaveBeenCalledOnce();
    });

    it("fires onClose when backdrop is clicked", () => {
      const { onClose } = renderModal(true);

      // The backdrop is the outermost div with the aria role set at the next level.
      // Click the backdrop element directly (identified by its fixed-inset style).
      const backdrop = screen.getByRole("dialog").parentElement;
      if (backdrop === null) throw new Error("Backdrop element not found in DOM.");

      // Simulate a click on the backdrop itself (not the dialog panel).
      fireEvent.click(backdrop, { target: backdrop });

      expect(onClose).toHaveBeenCalledOnce();
    });

    it("does not fire onClose when the dialog panel itself is clicked", async () => {
      const { onClose } = renderModal(true);

      await userEvent.click(screen.getByRole("dialog"));

      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe("when closed", () => {
    it("renders nothing when open is false", () => {
      renderModal(false);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
