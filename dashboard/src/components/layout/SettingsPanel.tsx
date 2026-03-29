/**
 * @packageDocumentation
 *
 * Right-side slide-out settings panel for the AutoApply dashboard.
 *
 * @remarks
 * Triggered by clicking Settings in the avatar dropdown ({@link TopBar}).
 * Renders a backdrop overlay and a 480 px panel flush to the right viewport
 * edge, spanning full viewport height. The panel contains three sections:
 * Base Resume upload, Candidate Profile upload, and Monthly Budget editing.
 */

import type { JSX } from "react";
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

/**
 * Right-side settings slide-out panel.
 *
 * @remarks
 * When `open` is true, renders a semi-transparent backdrop over the entire
 * viewport and a white panel from the right edge. Clicking the backdrop
 * calls `onClose`. Renders nothing when `open` is false.
 *
 * @param props - {@link SettingsPanelProps}
 * @returns The panel and backdrop elements, or `null` when closed.
 */
export function SettingsPanel({ open, onClose }: SettingsPanelProps): JSX.Element | null {
  if (!open) {
    return null;
  }

  return (
    <>
      {/* Backdrop — dims everything behind the panel including sidebar and topbar */}
      <div
        className="fixed inset-0 bg-black/25"
        style={{ zIndex: Z_SETTINGS_BACKDROP }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className="fixed inset-y-0 right-0 bg-white shadow-2xl flex flex-col"
        style={{ width: SETTINGS_PANEL_WIDTH_PX, zIndex: Z_SETTINGS_PANEL }}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
      >
        {/* Header */}
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

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-7 space-y-8">
          <BaseResumeSection />
          <CandidateProfileSection />
          <MonthlyBudgetSection />
        </div>
      </div>
    </>
  );
}

/**
 * Settings section for uploading and replacing the base resume YAML.
 *
 * @returns The base resume section element.
 */
function BaseResumeSection(): JSX.Element {
  return (
    <section className="space-y-4">
      <h3
        className="text-sm font-bold uppercase tracking-widest"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
      >
        Base Resume
      </h3>
      <FileCard
        icon="description"
        filename="base_resume.yaml"
        subtitle="Last updated: 2 days ago"
      />
      <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        This YAML file is the canonical starting point for all tailored resumes.
      </p>
      <GhostButton icon="upload_file" label="Replace Resume" />
    </section>
  );
}

/**
 * Settings section for uploading and replacing the candidate profile YAML.
 *
 * @returns The candidate profile section element.
 */
function CandidateProfileSection(): JSX.Element {
  return (
    <section className="space-y-4">
      <h3
        className="text-sm font-bold uppercase tracking-widest"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
      >
        Candidate Profile
      </h3>
      <FileCard
        icon="person"
        filename="candidate_profile.yaml"
        subtitle="Last modified: 5 days ago"
      />
      <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        Used by the gate classifier to score job fit. Contains your skills, experience, and
        preferences.
      </p>
      <GhostButton icon="edit_square" label="Replace Profile" />
    </section>
  );
}

/**
 * Settings section for configuring and viewing the monthly API spend budget.
 *
 * @returns The monthly budget section element.
 */
function MonthlyBudgetSection(): JSX.Element {
  /** Current spend in dollars — hardcoded mock until backend is wired. */
  const MOCK_SPENT_DOLLARS = 425;

  /** Monthly limit in dollars — shown in the input and progress bar. */
  const MOCK_LIMIT_DOLLARS = 500;

  const usedPercent = Math.round((MOCK_SPENT_DOLLARS / MOCK_LIMIT_DOLLARS) * 100);

  return (
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
              type="text"
              defaultValue={MOCK_LIMIT_DOLLARS.toFixed(2)}
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
              Spent: ${MOCK_SPENT_DOLLARS.toFixed(2)}
            </p>
            <p className="text-[10px]" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Remaining: ${(MOCK_LIMIT_DOLLARS - MOCK_SPENT_DOLLARS).toFixed(2)}
            </p>
          </div>
        </div>

        <button
          className="w-full py-4 text-white rounded-lg font-medium text-[14px] shadow-lg shadow-indigo-100 transition-all flex items-center justify-center gap-2"
          style={{ backgroundColor: "#6366f1" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = "#4f52de";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = "#6366f1";
          }}
        >
          <span
            className="material-symbols-outlined text-lg"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            save
          </span>
          Save Changes
        </button>
      </div>
    </section>
  );
}

/** Props for the reusable {@link FileCard} component. */
interface FileCardProps {
  /** Material Symbols icon name displayed on the left. */
  readonly icon: string;
  /** File name displayed as the primary label. */
  readonly filename: string;
  /** Secondary metadata line shown below the filename. */
  readonly subtitle: string;
}

/**
 * Displays a file artifact with its name, metadata, and View/Download actions.
 *
 * @param props - {@link FileCardProps}
 * @returns A styled file card element.
 */
function FileCard({ icon, filename, subtitle }: FileCardProps): JSX.Element {
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
          href="#"
          aria-label={`View ${filename}`}
        >
          View
        </a>
        <button
          className="transition-colors"
          style={{ color: COLOR_ON_SURFACE_VARIANT }}
          aria-label={`Download ${filename}`}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = COLOR_PRIMARY;
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = COLOR_ON_SURFACE_VARIANT;
          }}
        >
          <span className="material-symbols-outlined">download</span>
        </button>
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
}

/**
 * Ghost-style full-width button used for replace/upload actions in the settings panel.
 *
 * @param props - {@link GhostButtonProps}
 * @returns A styled button element.
 */
function GhostButton({ icon, label }: GhostButtonProps): JSX.Element {
  return (
    <button className="w-full py-3 bg-[#f3f4f6] hover:bg-[#e9eaec] rounded-2xl text-sm font-bold text-gray-600 transition-all flex items-center justify-center gap-2">
      <span className="material-symbols-outlined text-lg">{icon}</span>
      {label}
    </button>
  );
}
