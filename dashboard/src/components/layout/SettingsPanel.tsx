/**
 * @packageDocumentation
 *
 * Right-side slide-out settings panel for the AutoApply dashboard.
 */

import type { ChangeEvent, JSX } from "react";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBudget,
  fetchSettingsFiles,
  getProfileDownloadUrl,
  getResumeDownloadUrl,
  updateBudget,
  uploadProfile,
  uploadResume,
} from "@/lib/api/client";
import { formatUsd } from "@/lib/api/adapters";
import type { SettingsFileMetadataDto } from "@/lib/api/types";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
  SETTINGS_PANEL_WIDTH_PX,
  Z_SETTINGS_BACKDROP,
  Z_SETTINGS_PANEL,
} from "@/lib/design-tokens";

/** Props accepted by the {@link SettingsPanel} component. */
interface SettingsPanelProps {
  /** Whether the panel is currently visible. */
  readonly open: boolean;
  /** Callback invoked when the user closes the panel (X button or backdrop click). */
  readonly onClose: () => void;
}

/** Mutable upload target options used by the file-picker helper. */
type UploadTarget = "resume" | "profile";

/**
 * Convert settings file metadata into one compact subtitle string.
 *
 * @param metadata - File metadata from settings API.
 * @returns Human-readable subtitle string for file cards.
 */
function toFileSubtitle(metadata: SettingsFileMetadataDto): string {
  if (!metadata.exists) {
    return "File not found";
  }
  if (metadata.modified_at === null) {
    return `Size: ${metadata.size_bytes} bytes`;
  }
  const modifiedAt = new Date(metadata.modified_at).toLocaleString();
  return `Last modified: ${modifiedAt}`;
}

/**
 * Right-side settings slide-out panel.
 *
 * @param props - {@link SettingsPanelProps}
 * @returns The panel and backdrop elements, or `null` when closed.
 */
export function SettingsPanel({ open, onClose }: SettingsPanelProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const resumeInputRef = useRef<HTMLInputElement | null>(null);
  const profileInputRef = useRef<HTMLInputElement | null>(null);
  const [budgetInput, setBudgetInput] = useState<string>("0.00");

  const filesQuery = useQuery({
    queryKey: ["settings", "files"],
    queryFn: fetchSettingsFiles,
    enabled: open,
  });
  const budgetQuery = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
    enabled: open,
  });

  useEffect(() => {
    if (budgetQuery.data !== undefined) {
      setBudgetInput(budgetQuery.data.monthly_budget_usd.toFixed(2));
    }
  }, [budgetQuery.data]);

  const budgetMutation = useMutation({
    mutationFn: updateBudget,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileMutation = useMutation({
    mutationFn: uploadProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  if (!open) {
    return null;
  }

  const budgetData = budgetQuery.data;
  const usedPercent = Math.max(0, Math.min(100, Math.round(budgetData?.utilization_pct ?? 0)));

  function openFilePicker(target: UploadTarget): void {
    if (target === "resume") {
      resumeInputRef.current?.click();
      return;
    }
    profileInputRef.current?.click();
  }

  function handleBudgetSave(): void {
    const parsed = Number.parseFloat(budgetInput);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return;
    }
    budgetMutation.mutate(parsed);
  }

  function handleResumeUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    resumeMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleProfileUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    profileMutation.mutate(selectedFile);
    event.target.value = "";
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/25"
        style={{ zIndex: Z_SETTINGS_BACKDROP }}
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        className="fixed inset-y-0 right-0 bg-white shadow-2xl flex flex-col"
        style={{ width: SETTINGS_PANEL_WIDTH_PX, zIndex: Z_SETTINGS_PANEL }}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
      >
        <div className="p-6 bg-white flex items-center justify-between mb-2">
          <h2
            className="text-[20px] font-semibold tracking-tight"
            style={{ color: COLOR_ON_SURFACE }}
          >
            Settings
          </h2>
          <button
            className="p-2 text-gray-400 hover:bg-slate-50 rounded-full transition-colors"
            onClick={onClose}
            aria-label="Close settings"
          >
            <span className="material-symbols-outlined text-2xl">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-7 space-y-8 pb-8">
          <section className="space-y-4">
            <h3
              className="text-sm font-bold uppercase tracking-widest"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Base Resume
            </h3>
            <input
              ref={resumeInputRef}
              className="hidden"
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              onChange={handleResumeUpload}
            />
            <FileCard
              icon="description"
              metadata={filesQuery.data?.resume}
              downloadUrl={getResumeDownloadUrl()}
            />
            <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              This YAML file is the canonical starting point for all tailored resumes.
            </p>
            <GhostButton
              icon="upload_file"
              label={resumeMutation.isPending ? "Uploading Resume..." : "Replace Resume"}
              onClick={() => {
                openFilePicker("resume");
              }}
              disabled={resumeMutation.isPending}
            />
          </section>

          <section className="space-y-4">
            <h3
              className="text-sm font-bold uppercase tracking-widest"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Candidate Profile
            </h3>
            <input
              ref={profileInputRef}
              className="hidden"
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              onChange={handleProfileUpload}
            />
            <FileCard
              icon="person"
              metadata={filesQuery.data?.profile}
              downloadUrl={getProfileDownloadUrl()}
            />
            <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Used by the gate classifier to score job fit. Contains your skills, experience, and
              preferences.
            </p>
            <GhostButton
              icon="edit_square"
              label={profileMutation.isPending ? "Uploading Profile..." : "Replace Profile"}
              onClick={() => {
                openFilePicker("profile");
              }}
              disabled={profileMutation.isPending}
            />
          </section>

          <section className="space-y-4 pb-8">
            <h3
              className="text-sm font-bold uppercase tracking-widest"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
            >
              Monthly Budget
            </h3>
            <div className="space-y-6">
              <div>
                <label
                  className="block text-xs font-bold mb-2 uppercase"
                  htmlFor="budget-limit-input"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                >
                  Budget Limit
                </label>
                <div className="relative">
                  <span
                    className="absolute left-4 top-1/2 -translate-y-1/2 font-bold"
                    style={{ color: COLOR_ON_SURFACE }}
                  >
                    $
                  </span>
                  <input
                    id="budget-limit-input"
                    className="w-full bg-[#f9fafb] border border-[#f0f0f0] rounded-xl py-3 pl-8 pr-4 font-bold focus:outline-none focus:ring-2"
                    style={{ color: COLOR_ON_SURFACE, outlineColor: `${COLOR_PRIMARY}66` }}
                    type="number"
                    min="0"
                    step="0.01"
                    value={budgetInput}
                    onChange={(event) => {
                      setBudgetInput(event.target.value);
                    }}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between text-xs font-bold">
                  <span style={{ color: COLOR_ON_SURFACE_VARIANT }}>Monthly Spend</span>
                  <span style={{ color: COLOR_PRIMARY }}>{usedPercent}% Utilization</span>
                </div>
                <div className="h-3 w-full bg-[#edeeef] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 rounded-full"
                    style={{ width: `${usedPercent}%` }}
                  />
                </div>
                <div className="flex justify-between items-center mt-1">
                  <p className="text-[10px]" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    Spent: {formatUsd(budgetData?.spent_usd ?? 0)}
                  </p>
                  <p className="text-[10px]" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                    Remaining: {formatUsd(budgetData?.remaining_usd ?? 0)}
                  </p>
                </div>
              </div>

              <button
                className="w-full py-4 text-white rounded-lg font-medium text-[14px] shadow-lg shadow-indigo-100 transition-all flex items-center justify-center gap-2"
                style={{ backgroundColor: "#6366f1" }}
                onClick={handleBudgetSave}
                disabled={budgetMutation.isPending}
                onMouseEnter={(event) => {
                  event.currentTarget.style.backgroundColor = "#4f52de";
                }}
                onMouseLeave={(event) => {
                  event.currentTarget.style.backgroundColor = "#6366f1";
                }}
              >
                <span
                  className="material-symbols-outlined text-lg"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  save
                </span>
                {budgetMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </section>

          {(filesQuery.isError || budgetQuery.isError || resumeMutation.isError || profileMutation.isError) && (
            <p className="text-xs text-red-600">Some settings actions failed. Use Sync now and retry.</p>
          )}
        </div>
      </div>
    </>
  );
}

/** Props for the reusable {@link FileCard} component. */
interface FileCardProps {
  /** Material Symbols icon name displayed on the left. */
  readonly icon: string;
  /** File metadata from settings API. */
  readonly metadata?: SettingsFileMetadataDto;
  /** Download endpoint URL. */
  readonly downloadUrl: string;
}

/**
 * Displays one settings file artifact with metadata and download action.
 *
 * @param props - {@link FileCardProps}
 * @returns One styled file metadata card.
 */
function FileCard({ icon, metadata, downloadUrl }: FileCardProps): JSX.Element {
  const filename = metadata?.filename ?? "Loading...";
  const subtitle = metadata === undefined ? "Loading metadata..." : toFileSubtitle(metadata);

  return (
    <div className="p-4 bg-[#f9fafb] rounded-2xl border border-[#f0f0f0] flex items-center gap-4">
      <div className="w-12 h-12 bg-indigo-50 rounded-xl flex items-center justify-center text-indigo-600">
        <span className="material-symbols-outlined text-3xl">{icon}</span>
      </div>
      <div className="flex-1">
        <p className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE }}>
          {filename}
        </p>
        <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {subtitle}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <a
          className="text-indigo-600 text-sm font-bold hover:underline"
          href={downloadUrl}
          target="_blank"
          rel="noreferrer"
          aria-label={`View ${filename}`}
        >
          View
        </a>
        <a
          className="transition-colors"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
          href={downloadUrl}
          aria-label={`Download ${filename}`}
          onMouseEnter={(event) => {
            event.currentTarget.style.color = COLOR_PRIMARY;
          }}
          onMouseLeave={(event) => {
            event.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
          }}
        >
          <span className="material-symbols-outlined">download</span>
        </a>
      </div>
    </div>
  );
}

/** Props for the {@link GhostButton} component. */
interface GhostButtonProps {
  /** Material Symbols icon name shown to the left of the label. */
  readonly icon: string;
  /** Button label text. */
  readonly label: string;
  /** Click callback. */
  readonly onClick: () => void;
  /** Disabled state. */
  readonly disabled?: boolean;
}

/**
 * Ghost-style full-width action button used for replace/upload actions.
 *
 * @param props - {@link GhostButtonProps}
 * @returns A styled button element.
 */
function GhostButton({ icon, label, onClick, disabled = false }: GhostButtonProps): JSX.Element {
  return (
    <button
      className="w-full py-3 bg-[#f3f4f6] hover:bg-[#e9eaec] rounded-2xl text-sm font-bold text-gray-600 transition-all flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
      onClick={onClick}
      disabled={disabled}
    >
      <span className="material-symbols-outlined text-lg">{icon}</span>
      {label}
    </button>
  );
}
