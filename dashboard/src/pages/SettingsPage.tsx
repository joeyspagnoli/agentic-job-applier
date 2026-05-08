/**
 * @packageDocumentation
 *
 * Tabbed settings page shell. Routes between the General, AI Provider,
 * Profile & Resume, and Filters & Sources tabs while aggregating dirty/error
 * state from each child section.
 */

import type { JSX } from "react";
import { useCallback, useState } from "react";
import {
  COLOR_ERROR,
  COLOR_ERROR_CONTAINER,
  COLOR_ON_ERROR_CONTAINER,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_ON_WARNING_CONTAINER,
  COLOR_OUTLINE_VARIANT,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { CONFIRM_SWITCH_MESSAGE, TOP_LEVEL_TABS } from "@/lib/settings/constants";
import type { TopLevelTab } from "@/lib/settings/types";
import { TabButton } from "@/components/settings/TabButton";
import { AIProviderSettings } from "@/pages/settings/AIProviderSettings";
import { CandidateSettings } from "@/pages/settings/CandidateSettings";
import { FiltersAndSourcesSettings } from "@/pages/settings/FiltersAndSourcesSettings";
import { GeneralSettings } from "@/pages/settings/GeneralSettings";

/** Section identifiers tracked by the shell for dirty/error aggregation. */
type SectionKey =
  | "budget"
  | "apiKeys"
  | "tier"
  | "profile"
  | "resume"
  | "filtersAndSources";

/**
 * Settings page component.
 *
 * @returns Full tabbed settings page with guided + advanced editors.
 */
export function SettingsPage(): JSX.Element {
  const [activeTopLevelTab, setActiveTopLevelTab] = useState<TopLevelTab>("general");
  const [dirtyMap, setDirtyMap] = useState<Record<SectionKey, boolean>>({
    budget: false,
    apiKeys: false,
    tier: false,
    profile: false,
    resume: false,
    filtersAndSources: false,
  });
  const [errorMap, setErrorMap] = useState<Record<SectionKey, boolean>>({
    budget: false,
    apiKeys: false,
    tier: false,
    profile: false,
    resume: false,
    filtersAndSources: false,
  });

  const setDirty = useCallback((key: SectionKey, isDirty: boolean): void => {
    setDirtyMap((current) => {
      if (current[key] === isDirty) {
        return current;
      }
      return { ...current, [key]: isDirty };
    });
  }, []);

  const setError = useCallback((key: SectionKey, hasError: boolean): void => {
    setErrorMap((current) => {
      if (current[key] === hasError) {
        return current;
      }
      return { ...current, [key]: hasError };
    });
  }, []);

  const handleBudgetDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("budget", isDirty),
    [setDirty],
  );
  const handleBudgetErrorChange = useCallback(
    (hasError: boolean) => setError("budget", hasError),
    [setError],
  );
  const handleApiKeysDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("apiKeys", isDirty),
    [setDirty],
  );
  const handleTierDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("tier", isDirty),
    [setDirty],
  );
  const handleProfileDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("profile", isDirty),
    [setDirty],
  );
  const handleProfileErrorChange = useCallback(
    (hasError: boolean) => setError("profile", hasError),
    [setError],
  );
  const handleResumeDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("resume", isDirty),
    [setDirty],
  );
  const handleResumeErrorChange = useCallback(
    (hasError: boolean) => setError("resume", hasError),
    [setError],
  );
  const handleFiltersAndSourcesDirtyChange = useCallback(
    (isDirty: boolean) => setDirty("filtersAndSources", isDirty),
    [setDirty],
  );
  const handleFiltersAndSourcesErrorChange = useCallback(
    (hasError: boolean) => setError("filtersAndSources", hasError),
    [setError],
  );

  const hasUnsavedChanges = Object.values(dirtyMap).some(Boolean);
  const hasAnyError = Object.values(errorMap).some(Boolean);

  function handleTopLevelTabChange(nextTab: TopLevelTab): void {
    if (nextTab === activeTopLevelTab) {
      return;
    }
    if (hasUnsavedChanges && !window.confirm(CONFIRM_SWITCH_MESSAGE)) {
      return;
    }
    setActiveTopLevelTab(nextTab);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Settings
            </h2>
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Configure budget, pipeline depth, candidate context, and source filters in one place.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {TOP_LEVEL_TABS.map((tab) => (
              <TabButton
                key={tab.id}
                active={activeTopLevelTab === tab.id}
                label={tab.label}
                onClick={() => handleTopLevelTabChange(tab.id)}
              />
            ))}
          </div>
        </div>

        {hasUnsavedChanges && (
          <div
            className="rounded-xl border px-4 py-3 text-sm"
            style={{
              borderColor: COLOR_WARNING,
              color: COLOR_ON_WARNING_CONTAINER,
              backgroundColor: COLOR_WARNING_CONTAINER,
            }}
          >
            You have unsaved changes. Save before switching tabs to avoid losing edits.
          </div>
        )}
      </section>

      {/*
        Each tab section is mounted only while active. The original implementation
        kept all draft state in this shell so it survived top-level tab switches;
        because the user must explicitly confirm "discard" via the warning above
        before navigating away with unsaved edits, remounting on tab change is
        consistent with that confirmation contract.
      */}

      {activeTopLevelTab === "general" && (
        <GeneralSettings
          onBudgetDirtyChange={handleBudgetDirtyChange}
          onBudgetErrorChange={handleBudgetErrorChange}
          onApiKeysDirtyChange={handleApiKeysDirtyChange}
          onTierDirtyChange={handleTierDirtyChange}
        />
      )}

      {activeTopLevelTab === "ai-provider" && (
        <section className="rounded-2xl border border-outline-variant/30 bg-white p-6">
          <AIProviderSettings />
        </section>
      )}

      {activeTopLevelTab === "candidate" && (
        <CandidateSettings
          onProfileDirtyChange={handleProfileDirtyChange}
          onProfileErrorChange={handleProfileErrorChange}
          onResumeDirtyChange={handleResumeDirtyChange}
          onResumeErrorChange={handleResumeErrorChange}
        />
      )}

      {activeTopLevelTab === "filters" && (
        <FiltersAndSourcesSettings
          onDirtyChange={handleFiltersAndSourcesDirtyChange}
          onErrorChange={handleFiltersAndSourcesErrorChange}
        />
      )}

      {hasAnyError && (
        <div
          className="rounded-xl border px-4 py-3 text-sm"
          style={{
            borderColor: COLOR_ERROR,
            color: COLOR_ON_ERROR_CONTAINER,
            backgroundColor: COLOR_ERROR_CONTAINER,
          }}
        >
          One or more settings actions failed. Inspect field values and retry.
        </div>
      )}

      <div
        className="rounded-xl border px-4 py-3 text-xs"
        style={{ borderColor: `${COLOR_OUTLINE_VARIANT}66`, color: COLOR_ON_SURFACE_VARIANT }}
      >
        Legacy upload/download endpoints remain available for compatibility.
      </div>
    </div>
  );
}
