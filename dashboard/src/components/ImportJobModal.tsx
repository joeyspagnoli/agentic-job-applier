/**
 * @packageDocumentation
 *
 * Manual job import modal with two modes: paste a job URL or paste a raw
 * description with company/title/location metadata.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Loader2, Upload, X } from "lucide-react";

import { importJob } from "@/lib/api/client";
import {
  COLOR_ERROR,
  COLOR_ERROR_CONTAINER,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_SUCCESS,
  COLOR_SUCCESS_CONTAINER,
  COLOR_SURFACE,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Props accepted by {@link ImportJobModal}. */
interface ImportJobModalProps {
  /** Whether the modal is currently visible. */
  readonly open: boolean;
  /** Callback fired when the modal should close. */
  readonly onClose: () => void;
  /** Optional callback fired after a successful import (e.g. to refresh a job list). */
  readonly onImported?: () => void;
}

/** The two supported import modes. */
type ImportMode = "url" | "text";

/** Discriminated submission state. */
type SubmitState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success" }
  | { status: "error"; message: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MODES: { key: ImportMode; label: string; icon: typeof Link }[] = [
  { key: "url", label: "Paste URL", icon: Link },
  { key: "text", label: "Paste Description", icon: Upload },
];

const AUTO_CLOSE_MS = 1500;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Full-screen modal overlay for manually importing a job posting by URL or
 * by pasting its raw description text.
 *
 * @param props - {@link ImportJobModalProps}
 */
export function ImportJobModal({ open, onClose, onImported }: ImportJobModalProps) {
  const [mode, setMode] = useState<ImportMode>("url");
  const [url, setUrl] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });

  const backdropRef = useRef<HTMLDivElement>(null);
  const autoCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Reset form when modal opens / closes --------------------------------

  useEffect(() => {
    if (open) {
      setMode("url");
      setUrl("");
      setCompany("");
      setTitle("");
      setLocation("");
      setDescription("");
      setSubmitState({ status: "idle" });
    }
    return () => {
      if (autoCloseTimer.current) {
        clearTimeout(autoCloseTimer.current);
      }
    };
  }, [open]);

  // ---- Escape key closes ---------------------------------------------------

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // ---- Backdrop click closes -----------------------------------------------

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === backdropRef.current) onClose();
    },
    [onClose],
  );

  // ---- Submit handler -------------------------------------------------------

  const canSubmit =
    submitState.status !== "loading" &&
    submitState.status !== "success" &&
    (mode === "url" ? url.trim().length > 0 : description.trim().length > 0);

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setSubmitState({ status: "loading" });

    try {
      await importJob(
        mode === "url"
          ? { mode: "url", url: url.trim() }
          : {
              mode: "text",
              company: company.trim() || undefined,
              title: title.trim() || undefined,
              location: location.trim() || undefined,
              description: description.trim(),
            },
      );
      setSubmitState({ status: "success" });
      onImported?.();
      autoCloseTimer.current = setTimeout(onClose, AUTO_CLOSE_MS);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Import failed. Please try again.";
      setSubmitState({ status: "error", message });
    }
  }, [canSubmit, mode, url, company, title, location, description, onClose, onImported]);

  // ---- Early return when closed ---------------------------------------------

  if (!open) return null;

  // ---- Render ---------------------------------------------------------------

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
        animation: "importModalFadeIn 200ms ease-out both",
      }}
    >
      {/* Inline keyframes */}
      <style>{`
        @keyframes importModalFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes importModalScaleIn {
          from { opacity: 0; transform: scale(0.95) translateY(8px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Import job"
        style={{
          width: "100%",
          maxWidth: 520,
          margin: "0 16px",
          borderRadius: 16,
          backgroundColor: COLOR_SURFACE,
          boxShadow: "0 24px 48px -12px rgba(42,36,56,0.18)",
          animation: "importModalScaleIn 250ms ease-out both",
          overflow: "hidden",
        }}
      >
        {/* ---- Header ---- */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "20px 24px 16px",
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: 18,
              fontWeight: 600,
              color: COLOR_ON_SURFACE,
            }}
          >
            Import Job
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 32,
              height: 32,
              borderRadius: 8,
              border: "none",
              background: "transparent",
              color: COLOR_ON_SURFACE_VARIANT,
              cursor: "pointer",
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* ---- Mode toggle ---- */}
        <div style={{ padding: "0 24px 16px" }}>
          <div
            style={{
              display: "flex",
              gap: 4,
              padding: 4,
              borderRadius: 10,
              backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
            }}
          >
            {MODES.map(({ key, label, icon: Icon }) => {
              const active = mode === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setMode(key);
                    setSubmitState({ status: "idle" });
                  }}
                  style={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 6,
                    padding: "8px 12px",
                    borderRadius: 8,
                    border: "none",
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: "pointer",
                    transition: "all 150ms ease",
                    backgroundColor: active ? COLOR_PRIMARY : "transparent",
                    color: active ? "#fff" : COLOR_ON_SURFACE_VARIANT,
                  }}
                >
                  <Icon size={14} />
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ---- Form body ---- */}
        <div style={{ padding: "0 24px 20px" }}>
          {mode === "url" ? (
            <FieldInput
              label="Job posting URL"
              placeholder="https://example.com/jobs/123"
              value={url}
              onChange={setUrl}
              autoFocus
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <FieldInput
                label="Company name"
                placeholder="Acme Corp"
                value={company}
                onChange={setCompany}
                autoFocus
              />
              <FieldInput
                label="Job title"
                placeholder="Senior Software Engineer"
                value={title}
                onChange={setTitle}
              />
              <FieldInput
                label="Location"
                placeholder="San Francisco, CA (or Remote)"
                value={location}
                onChange={setLocation}
              />
              <FieldTextarea
                label="Job description *"
                placeholder="Paste the full job description here..."
                value={description}
                onChange={setDescription}
              />
            </div>
          )}
        </div>

        {/* ---- Status messages ---- */}
        {submitState.status === "error" && (
          <div
            style={{
              margin: "0 24px 16px",
              padding: "10px 14px",
              borderRadius: 10,
              backgroundColor: COLOR_ERROR_CONTAINER,
              color: COLOR_ERROR,
              fontSize: 13,
              fontWeight: 500,
              lineHeight: 1.4,
            }}
          >
            {submitState.message}
          </div>
        )}

        {submitState.status === "success" && (
          <div
            style={{
              margin: "0 24px 16px",
              padding: "10px 14px",
              borderRadius: 10,
              backgroundColor: COLOR_SUCCESS_CONTAINER,
              color: COLOR_SUCCESS,
              fontSize: 13,
              fontWeight: 500,
              lineHeight: 1.4,
            }}
          >
            Job imported successfully.
          </div>
        )}

        {/* ---- Footer ---- */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 10,
            padding: "12px 24px 20px",
            borderTop: `1px solid ${COLOR_OUTLINE_VARIANT}`,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "8px 18px",
              borderRadius: 8,
              border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
              background: "transparent",
              fontSize: 13,
              fontWeight: 500,
              color: COLOR_ON_SURFACE_VARIANT,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={handleSubmit}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 20px",
              borderRadius: 8,
              border: "none",
              fontSize: 13,
              fontWeight: 600,
              color: "#fff",
              backgroundColor: canSubmit ? COLOR_PRIMARY : COLOR_OUTLINE_VARIANT,
              cursor: canSubmit ? "pointer" : "not-allowed",
              transition: "background-color 150ms ease",
            }}
          >
            {submitState.status === "loading" && (
              <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
            )}
            Import
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Shared inline style fragments for form fields. */
const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  fontSize: 12,
  fontWeight: 500,
  color: COLOR_ON_SURFACE_VARIANT,
};

const fieldInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: 8,
  border: `1px solid ${COLOR_OUTLINE_VARIANT}`,
  backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
  fontSize: 14,
  color: COLOR_ON_SURFACE,
  outline: "none",
  transition: "border-color 150ms ease",
  boxSizing: "border-box",
};

/** Props for the simple labelled text input. */
interface FieldInputProps {
  readonly label: string;
  readonly placeholder: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly autoFocus?: boolean;
}

function FieldInput({ label, placeholder, value, onChange, autoFocus }: FieldInputProps) {
  return (
    <label>
      <span style={fieldLabelStyle}>{label}</span>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        style={fieldInputStyle}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = COLOR_PRIMARY;
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = COLOR_OUTLINE_VARIANT;
        }}
      />
    </label>
  );
}

/** Props for the simple labelled textarea. */
interface FieldTextareaProps {
  readonly label: string;
  readonly placeholder: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
}

function FieldTextarea({ label, placeholder, value, onChange }: FieldTextareaProps) {
  return (
    <label>
      <span style={fieldLabelStyle}>{label}</span>
      <textarea
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={6}
        style={{
          ...fieldInputStyle,
          resize: "vertical",
          minHeight: 120,
          fontFamily: "inherit",
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = COLOR_PRIMARY;
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = COLOR_OUTLINE_VARIANT;
        }}
      />
    </label>
  );
}
