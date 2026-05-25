/**
 * @packageDocumentation
 *
 * Confirmation modal shown when a user clicks "Apply" without having
 * tailored their resume for the target job.
 *
 * @remarks
 * Two CTAs are offered:
 * - "Yes, tailor my resume" (primary) — triggers {@link NotTailoredModalProps.onTailorThenApply}.
 * - "No, skip tailoring" (secondary) — triggers {@link NotTailoredModalProps.onApply}.
 *
 * Closes on Escape key press or backdrop click.
 */

import type { JSX } from "react";
import { useCallback, useEffect, useRef } from "react";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_SURFACE,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Props accepted by {@link NotTailoredModal}. */
export interface NotTailoredModalProps {
  /** Whether the modal is currently visible. */
  readonly open: boolean;
  /** Callback fired when the modal should close without action. */
  readonly onClose: () => void;
  /**
   * Callback fired when the user chooses to apply without tailoring.
   *
   * @remarks
   * Caller should POST `/api/jobs/{jobHash}/apply` and close the modal.
   */
  readonly onApply: () => void;
  /**
   * Callback fired when the user chooses to tailor first, then apply.
   *
   * @remarks
   * Caller should POST tailor, poll until SUCCESS, then POST apply.
   */
  readonly onTailorThenApply: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Modal overlay asking the user to confirm applying without a tailored resume.
 *
 * @param props - {@link NotTailoredModalProps}
 * @returns The modal overlay, or null when closed.
 */
export function NotTailoredModal({
  open,
  onClose,
  onApply,
  onTailorThenApply,
}: NotTailoredModalProps): JSX.Element | null {
  const backdropRef = useRef<HTMLDivElement>(null);

  // Close on Escape key.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  // Close on backdrop click (not panel click).
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === backdropRef.current) onClose();
    },
    [onClose],
  );

  if (!open) return null;

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(42, 36, 56, 0.45)",
        animation: "notTailoredModalFadeIn 200ms ease-out both",
      }}
    >
      {/* Inline keyframes — scoped to this overlay. */}
      <style>{`
        @keyframes notTailoredModalFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes notTailoredModalScaleIn {
          from { opacity: 0; transform: scale(0.95) translateY(8px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="not-tailored-modal-title"
        style={{
          width: "100%",
          maxWidth: 480,
          margin: "0 16px",
          borderRadius: 16,
          backgroundColor: COLOR_SURFACE,
          boxShadow: "0 24px 48px -12px rgba(42,36,56,0.18)",
          animation: "notTailoredModalScaleIn 250ms ease-out both",
          overflow: "hidden",
          padding: "28px 28px 24px",
        }}
      >
        {/* ---- Title ---- */}
        <h2
          id="not-tailored-modal-title"
          style={{
            margin: "0 0 12px",
            fontSize: 18,
            fontWeight: 600,
            color: COLOR_ON_SURFACE,
          }}
        >
          Resume not tailored
        </h2>

        {/* ---- Body ---- */}
        <p
          style={{
            margin: "0 0 8px",
            fontSize: 14,
            lineHeight: 1.6,
            color: COLOR_ON_SURFACE_VARIANT,
          }}
        >
          You haven&apos;t tailored your resume for this job yet. Tailoring rewrites your
          resume to highlight the skills and experience most relevant to this specific role,
          which typically improves your match rate.
        </p>
        <p
          style={{
            margin: "0 0 24px",
            fontSize: 14,
            lineHeight: 1.6,
            color: COLOR_ON_SURFACE_VARIANT,
          }}
        >
          Would you like to tailor your resume first before submitting the application?
        </p>

        {/* ---- Actions ---- */}
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
          {/* Secondary — skip tailoring */}
          <button
            type="button"
            onClick={onApply}
            style={{
              padding: "9px 18px",
              borderRadius: 10,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
              background: "transparent",
              fontSize: 13,
              fontWeight: 600,
              color: COLOR_ON_SURFACE_VARIANT,
              cursor: "pointer",
            }}
            className="scale-98-on-click transition-all"
          >
            No, skip tailoring
          </button>

          {/* Primary — tailor then apply */}
          <button
            type="button"
            onClick={onTailorThenApply}
            style={{
              padding: "9px 18px",
              borderRadius: 10,
              border: "none",
              background: COLOR_PRIMARY,
              fontSize: 13,
              fontWeight: 700,
              color: "#fff",
              cursor: "pointer",
            }}
            className="scale-98-on-click transition-all"
          >
            Yes, tailor my resume
          </button>
        </div>
      </div>
    </div>
  );
}
