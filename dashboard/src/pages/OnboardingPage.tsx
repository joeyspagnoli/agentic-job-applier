/**
 * @packageDocumentation
 *
 * Multi-step onboarding wizard for first-time AutoApply setup.
 *
 * @remarks
 * Guides the user through profile creation, target roles, resume upload,
 * hard filters, AI provider configuration, and optional company watchlist.
 * The shell owns all wizard state. Per-step UI lives in
 * `./onboarding/Step*.tsx`; pure helpers live under `@/lib/onboarding/`.
 * Re-exports at the bottom of this file preserve the public surface
 * consumed by `OnboardingPage.test.ts`.
 */

import type { JSX, ChangeEvent } from "react";
import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  uploadResume,
  uploadResumePdf,
  fetchSourcesSettings,
  updateSourcesYaml,
} from "@/lib/api/client";
import {
  COLOR_ERROR,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
} from "@/lib/design-tokens";
import {
  STEP_COUNT,
  WATCHLIST_WARNING_REDIRECT_DELAY_MS,
} from "@/lib/onboarding/constants";
import {
  defaultFiltersDraft,
  defaultProfileDraft,
  defaultProviderDraft,
  defaultRolesDraft,
  defaultWatchlistDraft,
} from "@/lib/onboarding/defaults";
import { finishOnboarding } from "@/lib/onboarding/finish-onboarding";
import type {
  FiltersDraft,
  ProfileDraft,
  ProviderDraft,
  RolesDraft,
  WatchlistDraft,
} from "@/lib/onboarding/types";
import { useCodexAuth } from "@/lib/onboarding/use-codex-auth";
import { buildWatchlistWarning } from "@/lib/onboarding/watchlist";
import { NavigationButtons } from "./onboarding/NavigationButtons";
import { ProgressIndicator } from "./onboarding/ProgressIndicator";
import { StepFilters } from "./onboarding/StepFilters";
import { StepProfile } from "./onboarding/StepProfile";
import { StepProvider } from "./onboarding/StepProvider";
import { StepResume } from "./onboarding/StepResume";
import { StepRoles } from "./onboarding/StepRoles";
import { StepWatchlist } from "./onboarding/StepWatchlist";
import { WarningBanner } from "./onboarding/WarningBanner";
import { WizardHeader } from "./onboarding/WizardHeader";

/**
 * Multi-step onboarding wizard page component.
 *
 * @returns The onboarding wizard page content.
 */
export function OnboardingPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [profile, setProfile] = useState<ProfileDraft>(defaultProfileDraft);
  const [roles, setRoles] = useState<RolesDraft>(defaultRolesDraft);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeUploaded, setResumeUploaded] = useState<boolean>(false);
  const [filters, setFilters] = useState<FiltersDraft>(defaultFiltersDraft);
  const [provider, setProvider] = useState<ProviderDraft>(defaultProviderDraft);
  const [watchlist, setWatchlist] = useState<WatchlistDraft>(defaultWatchlistDraft);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [notOnGreenhouseWarning, setNotOnGreenhouseWarning] = useState<string | null>(null);

  const resumeMutation = useMutation({
    mutationFn: (file: File) =>
      file.type === "application/pdf" ? uploadResumePdf(file) : uploadResume(file),
    onSuccess: () => {
      setResumeUploaded(true);
    },
  });

  const { start: startCodexAuthFlow } = useCodexAuth({ setProvider });

  const canAdvance = useCallback((): boolean => {
    if (currentStep === 0) {
      return profile.fullName.trim() !== "" && profile.email.trim() !== "";
    }
    if (currentStep === 1) {
      return roles.targetRoles.trim() !== "";
    }
    if (currentStep === 2) {
      return resumeUploaded;
    }
    return true;
  }, [currentStep, profile, roles, resumeUploaded]);

  /** Advance to the next wizard step. */
  function handleNext(): void {
    if (currentStep < STEP_COUNT - 1) {
      setError(null);
      setCurrentStep(currentStep + 1);
    }
  }

  /** Go back to the previous wizard step. */
  function handleBack(): void {
    if (currentStep > 0) {
      setError(null);
      setCurrentStep(currentStep - 1);
    }
  }

  /** Submit all wizard data and redirect to dashboard. */
  async function handleFinish(): Promise<void> {
    setSaving(true);
    setError(null);
    setWarning(null);
    setNotOnGreenhouseWarning(null);

    try {
      const watchlistResult = await finishOnboarding({
        profile,
        roles,
        filters,
        provider,
        watchlist,
        fetchSources: fetchSourcesSettings,
        updateSources: updateSourcesYaml,
        refetchOnboardingStatus: () =>
          queryClient.refetchQueries({ queryKey: ["onboarding-status"] }),
      });

      const { warning: warningMessage, notOnGreenhouseWarning: notOnGreenhouseMessage } =
        buildWatchlistWarning(watchlistResult);
      if (warningMessage !== null) setWarning(warningMessage);
      if (notOnGreenhouseMessage !== null) setNotOnGreenhouseWarning(notOnGreenhouseMessage);
      if (warningMessage !== null || notOnGreenhouseMessage !== null) {
        window.setTimeout(() => {
          navigate("/");
        }, WATCHLIST_WARNING_REDIRECT_DELAY_MS);
      } else {
        navigate("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  /**
   * Handle resume file selection.
   *
   * @param event - File input change event.
   */
  function handleResumeFile(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0] ?? null;
    setResumeFile(file);
    if (file) {
      resumeMutation.mutate(file);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-8"
      style={{ backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}
    >
      <div className="w-full max-w-2xl">
        <WizardHeader />

        <ProgressIndicator currentStep={currentStep} onStepClick={setCurrentStep} />

        <div
          className="rounded-2xl p-8 ambient-shadow border"
          style={{
            backgroundColor: "#ffffff",
            borderColor: `${COLOR_OUTLINE_VARIANT}30`,
          }}
        >
          {currentStep === 0 && <StepProfile draft={profile} onChange={setProfile} />}
          {currentStep === 1 && <StepRoles draft={roles} onChange={setRoles} />}
          {currentStep === 2 && (
            <StepResume
              file={resumeFile}
              uploaded={resumeUploaded}
              uploading={resumeMutation.isPending}
              onFileChange={handleResumeFile}
            />
          )}
          {currentStep === 3 && <StepFilters draft={filters} onChange={setFilters} />}
          {currentStep === 4 && (
            <StepProvider
              draft={provider}
              onChange={setProvider}
              onStartCodex={() => {
                void startCodexAuthFlow();
              }}
            />
          )}
          {currentStep === 5 && <StepWatchlist draft={watchlist} onChange={setWatchlist} />}

          {error && (
            <p className="mt-4 text-sm font-medium" style={{ color: COLOR_ERROR }}>
              {error}
            </p>
          )}
          {warning && (
            <WarningBanner
              message={warning}
              onDismiss={() => setWarning(null)}
              marginTopClass="mt-4"
            />
          )}
          {notOnGreenhouseWarning && (
            <WarningBanner
              message={notOnGreenhouseWarning}
              onDismiss={() => setNotOnGreenhouseWarning(null)}
              marginTopClass="mt-2"
            />
          )}

          <NavigationButtons
            currentStep={currentStep}
            canAdvance={canAdvance()}
            saving={saving}
            onBack={handleBack}
            onNext={handleNext}
            onFinish={() => {
              void handleFinish();
            }}
          />
        </div>
      </div>
    </div>
  );
}

// ── Test compatibility re-exports ──────────────────────────────────
//
// `OnboardingPage.test.ts` imports the pure helpers from this module path.
// Re-exporting from the new lib modules keeps the test contract intact
// without touching the 1837-line test file.

export {
  buildFiltersYaml,
  buildGithubReposBlock,
  deriveRequireTitlePatterns,
  detectSimplifyCategories,
  extractDomainKeywords,
} from "@/lib/onboarding/yaml-builders";
export {
  buildWatchlistWarning,
  resolveGreenhouseSlug,
  saveWatchlistCompanies,
  seedGithubRepos,
  validateGreenhouseSlug,
} from "@/lib/onboarding/watchlist";
export type {
  FiltersDraft,
  RolesDraft,
  WatchlistSaveResult,
} from "@/lib/onboarding/types";
