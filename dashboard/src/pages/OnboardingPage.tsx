/**
 * @packageDocumentation
 *
 * Multi-step onboarding wizard for first-time AutoApply setup.
 *
 * @remarks
 * Guides the user through profile creation, target roles, resume upload,
 * hard filters, AI provider configuration, and optional company watchlist.
 * Skippable steps are marked; the wizard persists progress server-side.
 */

import type { JSX, ChangeEvent } from "react";
import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  updateProfileStructured,
  updateAiProviderSettings,
  startCodexAuth,
  fetchCodexAuthStatus,
  uploadResume,
  uploadResumePdf,
  updateFiltersYaml,
  fetchSourcesSettings,
  updateSourcesYaml,
} from "@/lib/api/client";
import type { AiProviderMode, AiProviderType } from "@/lib/api/client";
import {
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_SURFACE_CONTAINER_LOW,
  COLOR_ERROR,
  COLOR_SUCCESS,
} from "@/lib/design-tokens";

/** Total number of wizard steps. */
const STEP_COUNT = 6;

/** Step labels shown in the progress indicator. */
const STEP_LABELS = [
  "About You",
  "Target Roles",
  "Resume",
  "Filters",
  "AI Provider",
  "Watchlist",
] as const;

/** Draft state for step 1: basic profile info. */
interface ProfileDraft {
  fullName: string;
  email: string;
  phone: string;
  city: string;
  stateOrRegion: string;
  countryCode: string;
  linkedinUrl: string;
  githubUrl: string;
  portfolioUrl: string;
  summary: string;
}

/** Draft state for step 2: target roles and preferences. */
interface RolesDraft {
  targetRoles: string;
  strongestAreas: string;
  experienceHighlights: string;
  searchTerms: string;
}

/** Draft state for step 4: hard filters. */
interface FiltersDraft {
  minSalary: string;
  maxSalary: string;
  requireRemote: boolean;
  jobTypes: string[];
  excludeTitlePatterns: string;
  excludeCompanies: string;
}

/** Draft state for step 5: AI provider. */
interface ProviderDraft {
  mode: AiProviderMode;
  providerType: AiProviderType;
  apiKey: string;
  codexStatus: "idle" | "starting" | "running" | "completed" | "failed";
  codexUrl: string | null;
  codexCode: string | null;
}

/** Draft state for step 6: company watchlist. */
interface WatchlistDraft {
  companies: string;
}

/**
 * Build the default empty profile draft.
 *
 * @returns Fresh profile draft with empty fields.
 */
function defaultProfileDraft(): ProfileDraft {
  return {
    fullName: "",
    email: "",
    phone: "",
    city: "",
    stateOrRegion: "",
    countryCode: "US",
    linkedinUrl: "",
    githubUrl: "",
    portfolioUrl: "",
    summary: "",
  };
}

/**
 * Build the default empty roles draft.
 *
 * @returns Fresh roles draft.
 */
function defaultRolesDraft(): RolesDraft {
  return {
    targetRoles: "",
    strongestAreas: "",
    experienceHighlights: "",
    searchTerms: "",
  };
}

/**
 * Build the default filters draft.
 *
 * @returns Fresh filters draft.
 */
function defaultFiltersDraft(): FiltersDraft {
  return {
    minSalary: "",
    maxSalary: "",
    requireRemote: false,
    jobTypes: ["Full-time"],
    excludeTitlePatterns: "",
    excludeCompanies: "",
  };
}

/**
 * Build the default provider draft.
 *
 * @returns Fresh provider draft.
 */
function defaultProviderDraft(): ProviderDraft {
  return {
    mode: "byok",
    providerType: "openai",
    apiKey: "",
    codexStatus: "idle",
    codexUrl: null,
    codexCode: null,
  };
}

/**
 * Serialize the onboarding filters draft to a filters.yaml string.
 *
 * @param draft - The filters draft state from the onboarding wizard.
 * @returns YAML string ready to write to filters.yaml.
 */
function buildFiltersYaml(draft: FiltersDraft): string {
  const minSalary = parseInt(draft.minSalary, 10) || 0;
  const maxSalary = parseInt(draft.maxSalary, 10) || 0;
  const excludeTitles = draft.excludeTitlePatterns
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => `(?i)${s}`);
  const excludeCompanies = draft.excludeCompanies
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const lines: string[] = [
    "hard_filters:",
    `  min_salary_usd: ${minSalary}`,
    `  max_salary_usd: ${maxSalary}`,
    `  require_remote: ${draft.requireRemote}`,
    "  exclude_companies:",
    ...excludeCompanies.map((c) => `    - "${c}"`),
    "  exclude_title_patterns:",
    ...excludeTitles.map((t) => `    - "${t}"`),
    "  exclude_job_types: []",
    "  require_title_patterns: []",
    "  exclude_locations: []",
    "  max_days_old: 30",
  ];
  return lines.join("\n");
}

/**
 * Merge watchlist company names into the greenhouse_companies list in sources YAML.
 *
 * @param companiesText - Newline-separated company names from the watchlist step.
 * @param updateSources - API function to write sources YAML.
 * @param fetchSources - API function to read current sources YAML.
 * @returns Nothing.
 */
async function saveWatchlistCompanies(
  companiesText: string,
  updateSources: (yaml: string) => Promise<unknown>,
  fetchSources: () => Promise<{ yaml_text: string }>,
): Promise<void> {
  const companyNames = companiesText
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  if (companyNames.length === 0) {
    return;
  }

  const current = await fetchSources();
  const newEntries = companyNames.map((name) => {
    const key = name.trim();
    const id = key.toLowerCase().replace(/\s+/g, "");
    return `  ${key}:\n    greenhouse_id: "${id}"\n    priority: 3`;
  });
  const appendBlock = newEntries.join("\n") + "\n";

  let updatedYaml = current.yaml_text ?? "";
  if (updatedYaml.includes("greenhouse_companies:")) {
    updatedYaml = updatedYaml.replace(
      /(greenhouse_companies:\s*\n)/,
      `$1${appendBlock}`,
    );
  } else {
    updatedYaml = updatedYaml + "\ngreenhouse_companies:\n" + appendBlock;
  }

  await updateSources(updatedYaml);
}

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
  const [watchlist, setWatchlist] = useState<WatchlistDraft>({ companies: "" });
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const resumeMutation = useMutation({
    mutationFn: (file: File) =>
      file.type === "application/pdf" ? uploadResumePdf(file) : uploadResume(file),
    onSuccess: () => {
      setResumeUploaded(true);
    },
  });

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

  /**
   * Advance to the next wizard step.
   *
   * @returns Nothing.
   */
  function handleNext(): void {
    if (currentStep < STEP_COUNT - 1) {
      setError(null);
      setCurrentStep(currentStep + 1);
    }
  }

  /**
   * Go back to the previous wizard step.
   *
   * @returns Nothing.
   */
  function handleBack(): void {
    if (currentStep > 0) {
      setError(null);
      setCurrentStep(currentStep - 1);
    }
  }

  /**
   * Submit all wizard data and redirect to dashboard.
   *
   * @returns Nothing.
   */
  async function handleFinish(): Promise<void> {
    setSaving(true);
    setError(null);

    try {
      await updateProfileStructured({
        profile: {
          summary: profile.summary,
          contact: {
            full_name: profile.fullName,
            email: profile.email,
            phone: profile.phone,
            city: profile.city,
            state_or_region: profile.stateOrRegion,
            country_code: profile.countryCode,
            country_label: "",
            linkedin_url: profile.linkedinUrl,
            github_url: profile.githubUrl,
            portfolio_url: profile.portfolioUrl,
          },
          work_authorization: {
            citizenship_country_code: profile.countryCode,
            citizenship_country_label: "",
            authorized_to_work_us: "unknown",
            requires_sponsorship_now_or_future: "unknown",
          },
          education_summary: "",
          education_entries: [],
          target_roles: splitLines(roles.targetRoles),
          strongest_areas: splitLines(roles.strongestAreas),
          experience_highlights: splitLines(roles.experienceHighlights),
          hard_filters: splitLines(filters.excludeTitlePatterns),
          preferences: [],
        },
        search_defaults: {
          job_board_search_terms: splitLines(roles.searchTerms),
        },
        prompt_context: null,
      });

      if (provider.mode === "byok" && provider.apiKey.trim() !== "") {
        await updateAiProviderSettings({
          mode: "byok",
          provider_type: provider.providerType,
          api_key: provider.apiKey,
        });
      }

      const filtersYaml = buildFiltersYaml(filters);
      await updateFiltersYaml(filtersYaml);

      if (watchlist.companies.trim() !== "") {
        await saveWatchlistCompanies(watchlist.companies, updateSourcesYaml, fetchSourcesSettings);
      }

      await queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  /**
   * Initiate Codex device auth and poll for completion.
   *
   * @returns Nothing.
   */
  async function handleStartCodexAuth(): Promise<void> {
    setProvider((prev) => ({ ...prev, codexStatus: "starting" }));

    try {
      const snapshot = await startCodexAuth();
      setProvider((prev) => ({
        ...prev,
        codexStatus: snapshot.status === "running" ? "running" : "starting",
        codexUrl: snapshot.verification_url,
        codexCode: snapshot.device_code,
      }));

      pollCodexAuth();
    } catch {
      setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
    }
  }

  /**
   * Poll Codex auth status every 3 seconds until completed or failed.
   *
   * @returns Nothing.
   */
  function pollCodexAuth(): void {
    const intervalId = window.setInterval(async () => {
      try {
        const status = await fetchCodexAuthStatus();
        setProvider((prev) => ({
          ...prev,
          codexStatus: status.status,
          codexUrl: status.verification_url ?? prev.codexUrl,
          codexCode: status.device_code ?? prev.codexCode,
        }));

        if (status.status === "completed" || status.status === "failed") {
          window.clearInterval(intervalId);
        }
      } catch {
        window.clearInterval(intervalId);
        setProvider((prev) => ({ ...prev, codexStatus: "failed" }));
      }
    }, 3000);
  }

  /**
   * Handle resume file selection.
   *
   * @param event - File input change event.
   * @returns Nothing.
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
        {/* Header */}
        <div className="text-center mb-10">
          <div className="flex justify-center mb-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center signature-gradient">
              <span
                className="material-symbols-outlined text-white text-2xl"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                bolt
              </span>
            </div>
          </div>
          <h1
            className="text-fluid-2xl font-extrabold tracking-tight mb-2"
            style={{ color: COLOR_ON_SURFACE }}
          >
            Welcome to AutoApply
          </h1>
          <p className="text-fluid-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Let&apos;s set up your job search profile in a few quick steps.
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEP_LABELS.map((label, idx) => (
            <div key={label} className="flex items-center gap-2">
              <button
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200"
                style={{
                  backgroundColor: idx === currentStep ? COLOR_PRIMARY : idx < currentStep ? COLOR_PRIMARY_FIXED : "transparent",
                  color: idx === currentStep ? "#ffffff" : idx < currentStep ? COLOR_PRIMARY : COLOR_OUTLINE,
                }}
                onClick={() => {
                  if (idx <= currentStep) {
                    setCurrentStep(idx);
                  }
                }}
              >
                {idx < currentStep ? (
                  <span className="material-symbols-outlined text-[14px]">check</span>
                ) : (
                  <span className="text-[11px] font-bold">{idx + 1}</span>
                )}
                <span className="hidden sm:inline">{label}</span>
              </button>
              {idx < STEP_COUNT - 1 && (
                <div
                  className="w-6 h-px"
                  style={{ backgroundColor: idx < currentStep ? COLOR_PRIMARY : COLOR_OUTLINE_VARIANT }}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content card */}
        <div
          className="rounded-2xl p-8 ambient-shadow border"
          style={{
            backgroundColor: "#ffffff",
            borderColor: `${COLOR_OUTLINE_VARIANT}30`,
          }}
        >
          {currentStep === 0 && (
            <StepProfile draft={profile} onChange={setProfile} />
          )}
          {currentStep === 1 && (
            <StepRoles draft={roles} onChange={setRoles} />
          )}
          {currentStep === 2 && (
            <StepResume
              file={resumeFile}
              uploaded={resumeUploaded}
              uploading={resumeMutation.isPending}
              onFileChange={handleResumeFile}
            />
          )}
          {currentStep === 3 && (
            <StepFilters draft={filters} onChange={setFilters} />
          )}
          {currentStep === 4 && (
            <StepProvider
              draft={provider}
              onChange={setProvider}
              onStartCodex={() => {
                void handleStartCodexAuth();
              }}
            />
          )}
          {currentStep === 5 && (
            <StepWatchlist draft={watchlist} onChange={setWatchlist} />
          )}

          {error && (
            <p className="mt-4 text-sm font-medium" style={{ color: COLOR_ERROR }}>
              {error}
            </p>
          )}

          {/* Navigation buttons */}
          <div className="flex justify-between items-center mt-8 pt-6 border-t" style={{ borderColor: `${COLOR_OUTLINE_VARIANT}30` }}>
            <button
              className="px-4 py-2 rounded-xl text-sm font-semibold transition-colors"
              style={{
                color: currentStep === 0 ? COLOR_OUTLINE : COLOR_ON_SURFACE_VARIANT,
                opacity: currentStep === 0 ? 0.4 : 1,
              }}
              disabled={currentStep === 0}
              onClick={handleBack}
            >
              Back
            </button>

            <div className="flex gap-3">
              {currentStep < STEP_COUNT - 1 && currentStep >= 2 && (
                <button
                  className="px-4 py-2 rounded-xl text-sm font-medium transition-colors"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  onClick={handleNext}
                >
                  Skip
                </button>
              )}
              {currentStep < STEP_COUNT - 1 ? (
                <button
                  className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
                  style={{ backgroundColor: COLOR_PRIMARY }}
                  disabled={!canAdvance()}
                  onClick={handleNext}
                >
                  Continue
                </button>
              ) : (
                <button
                  className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all duration-150 scale-98-on-click disabled:opacity-50"
                  style={{ backgroundColor: COLOR_PRIMARY }}
                  disabled={saving}
                  onClick={() => {
                    void handleFinish();
                  }}
                >
                  {saving ? "Saving..." : "Finish Setup"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step Components ────────────────────────────────────────────────

/** Props for an individual form input. */
interface FieldProps {
  /** Label text above the input. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Change callback. */
  readonly onChange: (value: string) => void;
  /** Input placeholder. */
  readonly placeholder?: string;
  /** Input type. */
  readonly type?: string;
  /** Whether to render a textarea instead. */
  readonly multiline?: boolean;
  /** Whether the field is required. */
  readonly required?: boolean;
}

/**
 * Reusable form field with label.
 *
 * @param props - {@link FieldProps}
 * @returns Labeled input element.
 */
function Field({ label, value, onChange, placeholder, type = "text", multiline, required }: FieldProps): JSX.Element {
  const inputClasses = "w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors focus:ring-2 focus:ring-primary/30";
  const inputStyle = {
    borderColor: COLOR_OUTLINE_VARIANT,
    color: COLOR_ON_SURFACE,
    backgroundColor: COLOR_SURFACE_CONTAINER_LOW,
  };

  return (
    <label className="block">
      <span className="text-xs font-semibold mb-1.5 block" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        {label}
        {required && <span style={{ color: COLOR_ERROR }}> *</span>}
      </span>
      {multiline ? (
        <textarea
          className={inputClasses}
          style={inputStyle}
          value={value}
          onChange={(e) => { onChange(e.target.value); }}
          placeholder={placeholder}
          rows={4}
        />
      ) : (
        <input
          className={inputClasses}
          style={inputStyle}
          type={type}
          value={value}
          onChange={(e) => { onChange(e.target.value); }}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}

/**
 * Step 1: Basic profile information.
 *
 * @param props - Profile draft and change handler.
 * @returns Profile form fields.
 */
function StepProfile({ draft, onChange }: { draft: ProfileDraft; onChange: (d: ProfileDraft) => void }): JSX.Element {
  /**
   * Update a single profile field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof ProfileDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          About You
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Basic contact information for your applications.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Full Name" value={draft.fullName} onChange={(v) => { set("fullName", v); }} placeholder="Jane Doe" required />
        <Field label="Email" value={draft.email} onChange={(v) => { set("email", v); }} placeholder="jane@example.com" type="email" required />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Phone" value={draft.phone} onChange={(v) => { set("phone", v); }} placeholder="+1 555-0123" />
        <Field label="City" value={draft.city} onChange={(v) => { set("city", v); }} placeholder="San Francisco" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="State / Region" value={draft.stateOrRegion} onChange={(v) => { set("stateOrRegion", v); }} placeholder="California" />
        <Field label="Country Code" value={draft.countryCode} onChange={(v) => { set("countryCode", v); }} placeholder="US" />
      </div>
      <Field label="LinkedIn URL" value={draft.linkedinUrl} onChange={(v) => { set("linkedinUrl", v); }} placeholder="https://linkedin.com/in/..." />
      <Field label="Professional Summary" value={draft.summary} onChange={(v) => { set("summary", v); }} placeholder="Brief overview of your experience and goals..." multiline />
    </div>
  );
}

/**
 * Step 2: Target roles and search preferences.
 *
 * @param props - Roles draft and change handler.
 * @returns Roles form fields.
 */
function StepRoles({ draft, onChange }: { draft: RolesDraft; onChange: (d: RolesDraft) => void }): JSX.Element {
  /**
   * Update a single roles field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof RolesDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Target Roles
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          What positions are you looking for? One per line.
        </p>
      </div>
      <Field label="Target Roles" value={draft.targetRoles} onChange={(v) => { set("targetRoles", v); }} placeholder="Software Engineer&#10;Full Stack Developer&#10;Backend Engineer" multiline required />
      <Field label="Strongest Areas" value={draft.strongestAreas} onChange={(v) => { set("strongestAreas", v); }} placeholder="Python&#10;React&#10;System Design" multiline />
      <Field label="Experience Highlights" value={draft.experienceHighlights} onChange={(v) => { set("experienceHighlights", v); }} placeholder="5 years at FAANG&#10;Led team of 8 engineers&#10;Shipped products to 10M+ users" multiline />
      <Field label="Job Board Search Terms" value={draft.searchTerms} onChange={(v) => { set("searchTerms", v); }} placeholder="software engineer&#10;full stack developer&#10;python developer" multiline />
    </div>
  );
}

/** Props for the resume step. */
interface StepResumeProps {
  /** Currently selected file, if any. */
  readonly file: File | null;
  /** Whether upload succeeded. */
  readonly uploaded: boolean;
  /** Whether upload is in progress. */
  readonly uploading: boolean;
  /** File input change handler. */
  readonly onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Step 3: Resume upload.
 *
 * @param props - {@link StepResumeProps}
 * @returns Resume upload form.
 */
function StepResume({ file, uploaded, uploading, onFileChange }: StepResumeProps): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Resume
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Upload your resume as a PDF, YAML, or .tex file. You can refine the structured content later in Settings.
        </p>
      </div>
      <div
        className="border-2 border-dashed rounded-2xl p-8 text-center transition-colors"
        style={{ borderColor: COLOR_OUTLINE_VARIANT }}
      >
        <span
          className="material-symbols-outlined text-4xl mb-3 block"
          style={{ color: COLOR_OUTLINE }}
        >
          upload_file
        </span>
        <p className="text-sm font-medium mb-4" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {file ? file.name : "Drag and drop or click to select"}
        </p>
        <label
          className="inline-block px-5 py-2 rounded-xl text-sm font-bold cursor-pointer transition-all scale-98-on-click"
          style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
        >
          Choose File
          <input
            type="file"
            accept=".yaml,.yml,.tex,.pdf"
            className="hidden"
            onChange={onFileChange}
          />
        </label>
        {uploading && (
          <p className="text-xs mt-3 animate-pulse" style={{ color: COLOR_PRIMARY }}>
            Uploading...
          </p>
        )}
        {uploaded && file?.type === "application/pdf" && (
          <p className="text-xs mt-3 font-semibold" style={{ color: COLOR_SUCCESS }}>
            PDF uploaded — visit Settings → Resume to add your work experience and skills.
          </p>
        )}
        {uploaded && file?.type !== "application/pdf" && (
          <p className="text-xs mt-3 font-semibold" style={{ color: COLOR_SUCCESS }}>
            Resume uploaded successfully
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Step 4: Hard filters for job search.
 *
 * @param props - Filters draft and change handler.
 * @returns Filters form fields.
 */
function StepFilters({ draft, onChange }: { draft: FiltersDraft; onChange: (d: FiltersDraft) => void }): JSX.Element {
  /** All available job type options. */
  const jobTypeOptions = ["Full-time", "Part-time", "Contract", "Internship"];

  /**
   * Toggle a job type in the selected list.
   *
   * @param jt - Job type to toggle.
   */
  function toggleJobType(jt: string): void {
    const next = draft.jobTypes.includes(jt)
      ? draft.jobTypes.filter((t) => t !== jt)
      : [...draft.jobTypes, jt];
    onChange({ ...draft, jobTypes: next });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Filters
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Set hard filters to automatically exclude irrelevant jobs.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Min Salary (USD)" value={draft.minSalary} onChange={(v) => { onChange({ ...draft, minSalary: v }); }} placeholder="80000" type="number" />
        <Field label="Max Salary (USD)" value={draft.maxSalary} onChange={(v) => { onChange({ ...draft, maxSalary: v }); }} placeholder="200000" type="number" />
      </div>

      <div>
        <span className="text-xs font-semibold mb-2 block" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Job Types
        </span>
        <div className="flex flex-wrap gap-2">
          {jobTypeOptions.map((jt) => (
            <button
              key={jt}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border"
              style={{
                backgroundColor: draft.jobTypes.includes(jt) ? COLOR_PRIMARY_FIXED : "transparent",
                color: draft.jobTypes.includes(jt) ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                borderColor: draft.jobTypes.includes(jt) ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
              }}
              onClick={() => { toggleJobType(jt); }}
            >
              {jt}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={draft.requireRemote}
          onChange={(e) => { onChange({ ...draft, requireRemote: e.target.checked }); }}
          className="w-4 h-4 rounded accent-primary"
        />
        <span className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
          Only show remote/hybrid positions
        </span>
      </label>

      <Field
        label="Exclude Title Patterns (one per line)"
        value={draft.excludeTitlePatterns}
        onChange={(v) => { onChange({ ...draft, excludeTitlePatterns: v }); }}
        placeholder="intern&#10;junior&#10;director"
        multiline
      />
      <Field
        label="Exclude Companies (one per line)"
        value={draft.excludeCompanies}
        onChange={(v) => { onChange({ ...draft, excludeCompanies: v }); }}
        placeholder="Acme Corp&#10;Initech"
        multiline
      />
    </div>
  );
}

/** Props for the AI provider step. */
interface StepProviderProps {
  /** Current provider draft state. */
  readonly draft: ProviderDraft;
  /** Draft change handler. */
  readonly onChange: (d: ProviderDraft) => void;
  /** Callback to initiate Codex device auth. */
  readonly onStartCodex: () => void;
}

/**
 * Step 5: AI provider configuration.
 *
 * @param props - {@link StepProviderProps}
 * @returns AI provider setup form.
 */
function StepProvider({ draft, onChange, onStartCodex }: StepProviderProps): JSX.Element {
  /** BYOK provider options. */
  const providers: { value: AiProviderType; label: string }[] = [
    { value: "openai", label: "OpenAI" },
    { value: "anthropic", label: "Anthropic" },
    { value: "gemini", label: "Google Gemini" },
    { value: "openrouter", label: "OpenRouter" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          AI Provider
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Choose how AutoApply accesses AI for resume tailoring and job scoring.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "codex" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "codex" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "codex" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => { onChange({ ...draft, mode: "codex" }); }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">cloud</span>
          Codex (Subscription)
        </button>
        <button
          className="flex-1 px-4 py-3 rounded-xl text-sm font-semibold border transition-all"
          style={{
            backgroundColor: draft.mode === "byok" ? COLOR_PRIMARY_FIXED : "transparent",
            color: draft.mode === "byok" ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
            borderColor: draft.mode === "byok" ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
          }}
          onClick={() => { onChange({ ...draft, mode: "byok" }); }}
        >
          <span className="material-symbols-outlined text-lg align-middle mr-1">key</span>
          Bring Your Own Key
        </button>
      </div>

      {draft.mode === "codex" && (
        <div
          className="rounded-xl p-5 border"
          style={{ borderColor: `${COLOR_OUTLINE_VARIANT}40`, backgroundColor: COLOR_SURFACE_CONTAINER_LOW }}
        >
          {draft.codexStatus === "idle" && (
            <>
              <p className="text-sm mb-3" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Sign in with your Codex/OpenAI subscription. A browser window will open for authentication.
              </p>
              <button
                className="px-5 py-2 rounded-xl text-sm font-bold text-white transition-all scale-98-on-click"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Sign in with Codex
              </button>
            </>
          )}
          {(draft.codexStatus === "starting" || draft.codexStatus === "running") && (
            <div className="space-y-3">
              <p className="text-sm font-medium" style={{ color: COLOR_ON_SURFACE }}>
                Waiting for authentication...
              </p>
              {draft.codexUrl && (
                <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                  Open this URL and enter the code below:
                </p>
              )}
              {draft.codexUrl && (
                <a
                  href={draft.codexUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold underline"
                  style={{ color: COLOR_PRIMARY }}
                >
                  {draft.codexUrl}
                </a>
              )}
              {draft.codexCode && (
                <div
                  className="inline-block px-4 py-2 rounded-lg font-mono text-lg font-bold tracking-widest"
                  style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
                >
                  {draft.codexCode}
                </div>
              )}
              <p className="text-xs animate-pulse" style={{ color: COLOR_OUTLINE }}>
                Polling for completion...
              </p>
            </div>
          )}
          {draft.codexStatus === "completed" && (
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-lg" style={{ color: COLOR_SUCCESS }}>check_circle</span>
              <span className="text-sm font-semibold" style={{ color: COLOR_SUCCESS }}>
                Codex authentication complete
              </span>
            </div>
          )}
          {draft.codexStatus === "failed" && (
            <div className="space-y-2">
              <p className="text-sm font-medium" style={{ color: COLOR_ERROR }}>
                Authentication failed. Please try again.
              </p>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-white"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={onStartCodex}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}

      {draft.mode === "byok" && (
        <div className="space-y-4">
          <div>
            <span className="text-xs font-semibold mb-2 block" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Provider
            </span>
            <div className="flex flex-wrap gap-2">
              {providers.map((p) => (
                <button
                  key={p.value}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all"
                  style={{
                    backgroundColor: draft.providerType === p.value ? COLOR_PRIMARY_FIXED : "transparent",
                    color: draft.providerType === p.value ? COLOR_PRIMARY : COLOR_ON_SURFACE_VARIANT,
                    borderColor: draft.providerType === p.value ? `${COLOR_PRIMARY}40` : COLOR_OUTLINE_VARIANT,
                  }}
                  onClick={() => { onChange({ ...draft, providerType: p.value }); }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <Field
            label="API Key"
            value={draft.apiKey}
            onChange={(v) => { onChange({ ...draft, apiKey: v }); }}
            placeholder="sk-..."
            type="password"
          />
        </div>
      )}
    </div>
  );
}

/**
 * Step 6: Optional company watchlist.
 *
 * @param props - Watchlist draft and change handler.
 * @returns Watchlist form.
 */
function StepWatchlist({ draft, onChange }: { draft: WatchlistDraft; onChange: (d: WatchlistDraft) => void }): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Company Watchlist
          <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full" style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}>
            Optional
          </span>
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Add specific companies to track. Their career pages will be scanned for new openings.
        </p>
      </div>
      <Field
        label="Companies (one per line)"
        value={draft.companies}
        onChange={(v) => { onChange({ ...draft, companies: v }); }}
        placeholder="Stripe&#10;Notion&#10;Linear&#10;Vercel"
        multiline
      />
    </div>
  );
}

/**
 * Split multiline text into a trimmed string array, filtering out blanks.
 *
 * @param text - Raw multiline text.
 * @returns Array of non-empty trimmed lines.
 */
function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
