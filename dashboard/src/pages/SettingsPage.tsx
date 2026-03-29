/**
 * @packageDocumentation
 *
 * Full settings page with guided and advanced editors for budget, candidate
 * profile, and canonical resume content.
 */

import type { ChangeEvent, JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatUsd } from "@/lib/api/adapters";
import {
  fetchBudget,
  fetchProfileSettings,
  fetchResumeSettings,
  fetchSettingsFiles,
  getProfileDownloadUrl,
  getResumeDownloadUrl,
  updateBudget,
  updateProfileStructured,
  updateProfileYaml,
  updateResumeStructured,
  updateResumeYaml,
  uploadProfile,
  uploadResume,
  uploadResumeTex,
} from "@/lib/api/client";
import type {
  ResumeContentDto,
  ResumeSkillListingDto,
  SettingsProfileDto,
  SettingsResumeDto,
} from "@/lib/api/types";
import { configureYamlSchemas, PROFILE_EDITOR_MODEL_URI, RESUME_EDITOR_MODEL_URI } from "@/lib/monaco/yaml-config";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";

type CandidateTab = "guided" | "yaml" | "files";
type ResumeTab = "guided" | "yaml" | "tex" | "files";

const EDITOR_HEIGHT_PX = 420;

/**
 * Convert list items to a newline-separated textarea value.
 *
 * @param items - List of values to flatten.
 * @returns Newline-separated text.
 */
function listToLines(items: readonly string[]): string {
  return items.join("\n");
}

/**
 * Convert textarea content into normalized list values.
 *
 * @param value - Raw textarea value.
 * @returns Trimmed list with empty lines removed.
 */
function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Deep-clone settings profile response into mutable draft payload.
 *
 * @param response - Settings profile DTO from backend.
 * @returns Mutable profile draft object.
 */
function toProfileDraft(response: SettingsProfileDto): {
  profile: SettingsProfileDto["profile"];
  search_defaults: SettingsProfileDto["search_defaults"];
  prompt_context: string | null;
} {
  return {
    profile: {
      ...response.profile,
      target_roles: [...response.profile.target_roles],
      strongest_areas: [...response.profile.strongest_areas],
      experience_highlights: [...response.profile.experience_highlights],
      hard_filters: [...response.profile.hard_filters],
      preferences: [...response.profile.preferences],
    },
    search_defaults: {
      job_board_search_terms: [...response.search_defaults.job_board_search_terms],
    },
    prompt_context: response.prompt_context,
  };
}

/**
 * Deep-clone resume settings response into mutable draft payload.
 *
 * @param response - Resume settings DTO from backend.
 * @returns Mutable resume draft object.
 */
function toResumeDraft(response: SettingsResumeDto): ResumeContentDto {
  return JSON.parse(JSON.stringify(response.resume)) as ResumeContentDto;
}

/**
 * Build one predictable listing identifier with a numeric suffix.
 *
 * @param prefix - Prefix for generated ID.
 * @param existingIds - Existing IDs for collision detection.
 * @returns Newly generated identifier.
 */
function nextGeneratedId(prefix: string, existingIds: readonly string[]): string {
  let suffix = existingIds.length + 1;
  let candidateId = `${prefix}_${suffix}`;
  while (existingIds.includes(candidateId)) {
    suffix += 1;
    candidateId = `${prefix}_${suffix}`;
  }
  return candidateId;
}

/**
 * Settings page component.
 *
 * @returns Full settings page with guided and advanced editors.
 */
export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const resumeYamlInputRef = useRef<HTMLInputElement | null>(null);
  const profileYamlInputRef = useRef<HTMLInputElement | null>(null);
  const resumeTexInputRef = useRef<HTMLInputElement | null>(null);

  const [candidateTab, setCandidateTab] = useState<CandidateTab>("guided");
  const [resumeTab, setResumeTab] = useState<ResumeTab>("guided");
  const [budgetInput, setBudgetInput] = useState("0.00");
  const [profileDraft, setProfileDraft] = useState<ReturnType<typeof toProfileDraft> | null>(null);
  const [resumeDraft, setResumeDraft] = useState<ResumeContentDto | null>(null);
  const [profileYamlDraft, setProfileYamlDraft] = useState("");
  const [resumeYamlDraft, setResumeYamlDraft] = useState("");
  const [lastResumeMigrationSummary, setLastResumeMigrationSummary] = useState<string | null>(null);

  const budgetQuery = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
    refetchInterval: false,
  });
  const profileQuery = useQuery({
    queryKey: ["settings", "profile"],
    queryFn: fetchProfileSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const resumeQuery = useQuery({
    queryKey: ["settings", "resume"],
    queryFn: fetchResumeSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const filesQuery = useQuery({
    queryKey: ["settings", "files"],
    queryFn: fetchSettingsFiles,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (budgetQuery.data !== undefined) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBudgetInput(budgetQuery.data.monthly_budget_usd.toFixed(2));
    }
  }, [budgetQuery.data]);

  useEffect(() => {
    if (profileQuery.data !== undefined) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProfileDraft(toProfileDraft(profileQuery.data));
      setProfileYamlDraft(profileQuery.data.yaml_text);
    }
  }, [profileQuery.data]);

  useEffect(() => {
    if (resumeQuery.data !== undefined) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResumeDraft(toResumeDraft(resumeQuery.data));
      setResumeYamlDraft(resumeQuery.data.yaml_text);
    }
  }, [resumeQuery.data]);

  const budgetMutation = useMutation({
    mutationFn: updateBudget,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const profileStructuredMutation = useMutation({
    mutationFn: updateProfileStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileYamlMutation = useMutation({
    mutationFn: updateProfileYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileUploadMutation = useMutation({
    mutationFn: uploadProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeStructuredMutation = useMutation({
    mutationFn: updateResumeStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeYamlMutation = useMutation({
    mutationFn: updateResumeYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeUploadMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "resume"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeTexMutation = useMutation({
    mutationFn: uploadResumeTex,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setLastResumeMigrationSummary(
        `${response.migration.experience_listings} experience listings, ` +
          `${response.migration.project_listings} project listings, ` +
          `${response.migration.skill_rows} skills rows`,
      );
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const hasAnyError =
    budgetQuery.isError ||
    profileQuery.isError ||
    resumeQuery.isError ||
    filesQuery.isError ||
    budgetMutation.isError ||
    profileStructuredMutation.isError ||
    profileYamlMutation.isError ||
    profileUploadMutation.isError ||
    resumeStructuredMutation.isError ||
    resumeYamlMutation.isError ||
    resumeUploadMutation.isError ||
    resumeTexMutation.isError;

  const profileMetadata = profileQuery.data?.metadata ?? filesQuery.data?.profile;
  const resumeMetadata = resumeQuery.data?.metadata ?? filesQuery.data?.resume;
  const budgetUsedPct = Math.max(0, Math.min(100, Math.round(budgetQuery.data?.utilization_pct ?? 0)));

  const resumeCountsText = useMemo(() => {
    if (resumeQuery.data === undefined) {
      return "Loading resume counts...";
    }
    return [
      `${resumeQuery.data.counts.education_entries} education entries`,
      `${resumeQuery.data.counts.experience_listings} experience listings`,
      `${resumeQuery.data.counts.project_listings} project listings`,
      `${resumeQuery.data.counts.skill_rows} skills rows`,
    ].join(" • ");
  }, [resumeQuery.data]);

  function handleBudgetSave(): void {
    const parsedBudget = Number.parseFloat(budgetInput);
    if (!Number.isFinite(parsedBudget) || parsedBudget < 0) {
      return;
    }
    budgetMutation.mutate(parsedBudget);
  }

  function handleProfileListUpdate(
    fieldName: keyof SettingsProfileDto["profile"],
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    if (
      fieldName === "target_roles" ||
      fieldName === "strongest_areas" ||
      fieldName === "experience_highlights" ||
      fieldName === "hard_filters" ||
      fieldName === "preferences"
    ) {
      setProfileDraft({
        ...profileDraft,
        profile: {
          ...profileDraft.profile,
          [fieldName]: linesToList(value),
        },
      });
    }
  }

  function handleProfileScalarUpdate(
    fieldName: "summary" | "education" | "citizenship",
    value: string,
  ): void {
    if (profileDraft === null) {
      return;
    }
    setProfileDraft({
      ...profileDraft,
      profile: {
        ...profileDraft.profile,
        [fieldName]: value,
      },
    });
  }

  function handleProfileGuidedSave(): void {
    if (profileDraft === null) {
      return;
    }
    profileStructuredMutation.mutate({
      profile: profileDraft.profile,
      search_defaults: profileDraft.search_defaults,
      prompt_context: profileDraft.prompt_context,
    });
  }

  function handleProfileYamlSave(): void {
    profileYamlMutation.mutate(profileYamlDraft);
  }

  function handleProfileYamlUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    profileUploadMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeYamlUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    resumeUploadMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeTexUpload(event: ChangeEvent<HTMLInputElement>): void {
    const selectedFile = event.target.files?.[0];
    if (selectedFile === undefined) {
      return;
    }
    resumeTexMutation.mutate(selectedFile);
    event.target.value = "";
  }

  function handleResumeLayoutUpdate(fieldName: keyof ResumeContentDto["layout"], value: string): void {
    if (resumeDraft === null) {
      return;
    }
    const parsedValue = Number.parseFloat(value);
    if (!Number.isFinite(parsedValue)) {
      return;
    }
    setResumeDraft({
      ...resumeDraft,
      layout: {
        ...resumeDraft.layout,
        [fieldName]: parsedValue,
      },
    });
  }

  function handleExperienceListingFieldUpdate(
    index: number,
    fieldName: "id" | "title" | "date_range" | "organization" | "enabled",
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.experience.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      return {
        ...listing,
        [fieldName]: value,
      };
    });
    setResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: updatedListings,
      },
    });
  }

  function handleExperienceBulletsUpdate(index: number, value: string): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.experience.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      const nextBullets = linesToList(value).map((line, lineIndex) => ({
        id: `${listing.id || "exp"}_bullet_${lineIndex + 1}`,
        text: line,
      }));
      return {
        ...listing,
        bullets: nextBullets,
      };
    });
    setResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: updatedListings,
      },
    });
  }

  function addExperienceListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.experience.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("exp_new", existingIds);
    const nextListings = [
      ...resumeDraft.experience.listings,
      {
        id: nextId,
        enabled: true,
        title: "New Experience Role",
        date_range: "MM. YYYY -- MM. YYYY",
        organization: "Organization",
        bullets: [
          {
            id: `${nextId}_bullet_1`,
            text: "Add impact-focused bullet text here.",
          },
        ],
      },
    ];
    setResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: nextListings,
      },
    });
  }

  function removeExperienceListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    setResumeDraft({
      ...resumeDraft,
      experience: {
        ...resumeDraft.experience,
        listings: resumeDraft.experience.listings.filter((_listing, listingIndex) => listingIndex !== index),
      },
    });
  }

  function handleProjectListingFieldUpdate(
    index: number,
    fieldName: "id" | "title" | "date_range" | "tech_stack" | "enabled",
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.projects.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      return {
        ...listing,
        [fieldName]: value,
      };
    });
    setResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: updatedListings,
      },
    });
  }

  function handleProjectBulletsUpdate(index: number, value: string): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.projects.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      const nextBullets = linesToList(value).map((line, lineIndex) => ({
        id: `${listing.id || "project"}_bullet_${lineIndex + 1}`,
        text: line,
      }));
      return {
        ...listing,
        bullets: nextBullets,
      };
    });
    setResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: updatedListings,
      },
    });
  }

  function addProjectListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.projects.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("proj_new", existingIds);
    const nextListings = [
      ...resumeDraft.projects.listings,
      {
        id: nextId,
        enabled: true,
        title: "New Project",
        tech_stack: "Tech stack",
        date_range: "MM. YYYY -- MM. YYYY",
        bullets: [
          {
            id: `${nextId}_bullet_1`,
            text: "Add measurable project bullet text here.",
          },
        ],
      },
    ];
    setResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: nextListings,
      },
    });
  }

  function removeProjectListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    setResumeDraft({
      ...resumeDraft,
      projects: {
        ...resumeDraft.projects,
        listings: resumeDraft.projects.listings.filter((_listing, listingIndex) => listingIndex !== index),
      },
    });
  }

  function handleSkillListingUpdate(
    index: number,
    fieldName: keyof ResumeSkillListingDto,
    value: string | boolean,
  ): void {
    if (resumeDraft === null) {
      return;
    }
    const updatedListings = resumeDraft.skills_achievements.listings.map((listing, listingIndex) => {
      if (listingIndex !== index) {
        return listing;
      }
      return {
        ...listing,
        [fieldName]: value,
      };
    });
    setResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: updatedListings,
      },
    });
  }

  function addSkillListing(): void {
    if (resumeDraft === null) {
      return;
    }
    const existingIds = resumeDraft.skills_achievements.listings.map((listing) => listing.id);
    const nextId = nextGeneratedId("skill_new", existingIds);
    const nextListings = [
      ...resumeDraft.skills_achievements.listings,
      {
        id: nextId,
        enabled: true,
        category: "Category",
        text: "Skill text",
      },
    ];
    setResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: nextListings,
      },
    });
  }

  function removeSkillListing(index: number): void {
    if (resumeDraft === null) {
      return;
    }
    setResumeDraft({
      ...resumeDraft,
      skills_achievements: {
        ...resumeDraft.skills_achievements,
        listings: resumeDraft.skills_achievements.listings.filter(
          (_listing, listingIndex) => listingIndex !== index,
        ),
      },
    });
  }

  function handleResumeGuidedSave(): void {
    if (resumeDraft === null) {
      return;
    }
    resumeStructuredMutation.mutate(resumeDraft);
  }

  function handleResumeYamlSave(): void {
    resumeYamlMutation.mutate(resumeYamlDraft);
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <section className="bg-white rounded-2xl border border-slate-100 p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Monthly Budget
            </h2>
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Control monthly spend guardrails for pipeline API costs.
            </p>
          </div>
          <button
            className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
            style={{ backgroundColor: COLOR_PRIMARY }}
            onClick={handleBudgetSave}
            disabled={budgetMutation.isPending}
          >
            {budgetMutation.isPending ? "Saving..." : "Save Budget"}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Budget Limit (USD)
            <input
              className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
              type="number"
              min="0"
              step="0.01"
              value={budgetInput}
              onChange={(event) => {
                setBudgetInput(event.target.value);
              }}
            />
          </label>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs uppercase tracking-wide" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Spent
            </p>
            <p className="text-lg font-bold">{formatUsd(budgetQuery.data?.spent_usd ?? 0)}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs uppercase tracking-wide" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Remaining
            </p>
            <p className="text-lg font-bold">{formatUsd(budgetQuery.data?.remaining_usd ?? 0)}</p>
          </div>
        </div>
        <div className="space-y-2">
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-indigo-600 rounded-full" style={{ width: `${budgetUsedPct}%` }} />
          </div>
          <p className="text-xs text-right" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            {budgetUsedPct}% consumed
          </p>
        </div>
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 p-6 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Candidate Profile
            </h2>
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Edit gate-decider context without manual file juggling.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TabButton active={candidateTab === "guided"} label="Guided" onClick={() => setCandidateTab("guided")} />
            <TabButton active={candidateTab === "yaml"} label="Advanced YAML" onClick={() => setCandidateTab("yaml")} />
            <TabButton active={candidateTab === "files"} label="File Actions" onClick={() => setCandidateTab("files")} />
          </div>
        </div>

        {candidateTab === "guided" && profileDraft !== null && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <LabeledInput
                label="Summary"
                value={profileDraft.profile.summary}
                onChange={(value) => handleProfileScalarUpdate("summary", value)}
              />
              <LabeledInput
                label="Education"
                value={profileDraft.profile.education}
                onChange={(value) => handleProfileScalarUpdate("education", value)}
              />
              <LabeledInput
                label="Citizenship"
                value={profileDraft.profile.citizenship}
                onChange={(value) => handleProfileScalarUpdate("citizenship", value)}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <LabeledTextarea
                label="Target Roles (one per line)"
                value={listToLines(profileDraft.profile.target_roles)}
                onChange={(value) => handleProfileListUpdate("target_roles", value)}
              />
              <LabeledTextarea
                label="Strongest Areas (one per line)"
                value={listToLines(profileDraft.profile.strongest_areas)}
                onChange={(value) => handleProfileListUpdate("strongest_areas", value)}
              />
              <LabeledTextarea
                label="Experience Highlights (one per line)"
                value={listToLines(profileDraft.profile.experience_highlights)}
                onChange={(value) => handleProfileListUpdate("experience_highlights", value)}
              />
              <LabeledTextarea
                label="Hard Filters (one per line)"
                value={listToLines(profileDraft.profile.hard_filters)}
                onChange={(value) => handleProfileListUpdate("hard_filters", value)}
              />
              <LabeledTextarea
                label="Preferences (one per line)"
                value={listToLines(profileDraft.profile.preferences)}
                onChange={(value) => handleProfileListUpdate("preferences", value)}
              />
              <LabeledTextarea
                label="Search Terms (one per line)"
                value={listToLines(profileDraft.search_defaults.job_board_search_terms)}
                onChange={(value) => {
                  setProfileDraft({
                    ...profileDraft,
                    search_defaults: { job_board_search_terms: linesToList(value) },
                  });
                }}
              />
            </div>

            <LabeledTextarea
              label="Prompt Context Override (optional)"
              value={profileDraft.prompt_context ?? ""}
              onChange={(value) => {
                setProfileDraft({
                  ...profileDraft,
                  prompt_context: value.trim() === "" ? null : value,
                });
              }}
              rows={6}
            />

            <div className="flex justify-end">
              <button
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleProfileGuidedSave}
                disabled={profileStructuredMutation.isPending}
              >
                {profileStructuredMutation.isPending ? "Saving..." : "Save Guided Profile"}
              </button>
            </div>
          </div>
        )}

        {candidateTab === "yaml" && (
          <div className="space-y-4">
            <YamlEditor
              modelPath={PROFILE_EDITOR_MODEL_URI}
              value={profileYamlDraft}
              onChange={setProfileYamlDraft}
            />
            <div className="flex justify-end">
              <button
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleProfileYamlSave}
                disabled={profileYamlMutation.isPending}
              >
                {profileYamlMutation.isPending ? "Saving..." : "Save YAML"}
              </button>
            </div>
          </div>
        )}

        {candidateTab === "files" && (
          <div className="space-y-4">
            <SettingsFileCard
              title="Candidate Profile YAML"
              subtitle={profileMetadata?.modified_at ? new Date(profileMetadata.modified_at).toLocaleString() : "No file timestamp"}
              downloadUrl={getProfileDownloadUrl()}
            />
            <input
              ref={profileYamlInputRef}
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              className="hidden"
              onChange={handleProfileYamlUpload}
            />
            <button
              className="px-4 py-2 rounded-lg border border-slate-200 text-sm font-semibold"
              onClick={() => profileYamlInputRef.current?.click()}
              disabled={profileUploadMutation.isPending}
            >
              {profileUploadMutation.isPending ? "Uploading..." : "Replace Profile YAML"}
            </button>
          </div>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 p-6 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
              Resume Content
            </h2>
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Guided edits for listings and layout, with advanced YAML and TeX migration support.
            </p>
            <p className="text-xs mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              {resumeCountsText}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TabButton active={resumeTab === "guided"} label="Guided" onClick={() => setResumeTab("guided")} />
            <TabButton active={resumeTab === "yaml"} label="Advanced YAML" onClick={() => setResumeTab("yaml")} />
            <TabButton active={resumeTab === "tex"} label="Upload TeX" onClick={() => setResumeTab("tex")} />
            <TabButton active={resumeTab === "files"} label="File Actions" onClick={() => setResumeTab("files")} />
          </div>
        </div>

        {resumeTab === "guided" && resumeDraft !== null && (
          <div className="space-y-6">
            <div className="rounded-xl border border-slate-200 p-4 bg-slate-50">
              <h3 className="text-sm font-bold uppercase tracking-wide">Locked Sections (Read-Only)</h3>
              <p className="text-xs mt-2" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                Personal and education sections are locked by resume policy and cannot be edited here.
              </p>
              <p className="text-sm mt-3">
                <strong>{resumeDraft.personal.name}</strong> • {resumeDraft.personal.email} • {resumeDraft.personal.phone}
              </p>
              {resumeDraft.education.entries.map((entry) => (
                <div key={entry.id} className="mt-2 text-sm">
                  <p>
                    <strong>{entry.institution}</strong> ({entry.date_range})
                  </p>
                  <p>{entry.degree}</p>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-slate-200 p-4 space-y-4">
              <h3 className="text-sm font-bold uppercase tracking-wide">Layout Knobs</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                {Object.entries(resumeDraft.layout).map(([fieldName, fieldValue]) => (
                  <label key={fieldName} className="text-xs font-semibold">
                    {fieldName}
                    <input
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-sm"
                      type="number"
                      step="0.01"
                      value={fieldValue}
                      onChange={(event) => handleResumeLayoutUpdate(fieldName as keyof ResumeContentDto["layout"], event.target.value)}
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 p-4 space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-bold uppercase tracking-wide">Experience Listings</h3>
                <button className="text-sm font-semibold text-indigo-700" onClick={addExperienceListing}>
                  + Add Listing
                </button>
              </div>
              {resumeDraft.experience.listings.map((listing, index) => (
                <div key={listing.id} className="rounded-xl border border-slate-100 p-3 bg-slate-50 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <LabeledInput
                      label="ID"
                      value={listing.id}
                      onChange={(value) => handleExperienceListingFieldUpdate(index, "id", value)}
                    />
                    <LabeledInput
                      label="Title"
                      value={listing.title}
                      onChange={(value) => handleExperienceListingFieldUpdate(index, "title", value)}
                    />
                    <LabeledInput
                      label="Date Range"
                      value={listing.date_range}
                      onChange={(value) => handleExperienceListingFieldUpdate(index, "date_range", value)}
                    />
                    <LabeledInput
                      label="Organization"
                      value={listing.organization}
                      onChange={(value) => handleExperienceListingFieldUpdate(index, "organization", value)}
                    />
                  </div>
                  <LabeledTextarea
                    label="Bullets (one per line)"
                    value={listing.bullets.map((bullet) => bullet.text).join("\n")}
                    onChange={(value) => handleExperienceBulletsUpdate(index, value)}
                  />
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold">
                      <input
                        type="checkbox"
                        checked={listing.enabled}
                        onChange={(event) => handleExperienceListingFieldUpdate(index, "enabled", event.target.checked)}
                      />{" "}
                      Enabled
                    </label>
                    <button className="text-xs font-semibold text-red-600" onClick={() => removeExperienceListing(index)}>
                      Remove Listing
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-slate-200 p-4 space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-bold uppercase tracking-wide">Project Listings</h3>
                <button className="text-sm font-semibold text-indigo-700" onClick={addProjectListing}>
                  + Add Project
                </button>
              </div>
              {resumeDraft.projects.listings.map((listing, index) => (
                <div key={listing.id} className="rounded-xl border border-slate-100 p-3 bg-slate-50 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <LabeledInput
                      label="ID"
                      value={listing.id}
                      onChange={(value) => handleProjectListingFieldUpdate(index, "id", value)}
                    />
                    <LabeledInput
                      label="Title"
                      value={listing.title}
                      onChange={(value) => handleProjectListingFieldUpdate(index, "title", value)}
                    />
                    <LabeledInput
                      label="Tech Stack"
                      value={listing.tech_stack}
                      onChange={(value) => handleProjectListingFieldUpdate(index, "tech_stack", value)}
                    />
                    <LabeledInput
                      label="Date Range"
                      value={listing.date_range}
                      onChange={(value) => handleProjectListingFieldUpdate(index, "date_range", value)}
                    />
                  </div>
                  <LabeledTextarea
                    label="Bullets (one per line)"
                    value={listing.bullets.map((bullet) => bullet.text).join("\n")}
                    onChange={(value) => handleProjectBulletsUpdate(index, value)}
                  />
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold">
                      <input
                        type="checkbox"
                        checked={listing.enabled}
                        onChange={(event) => handleProjectListingFieldUpdate(index, "enabled", event.target.checked)}
                      />{" "}
                      Enabled
                    </label>
                    <button className="text-xs font-semibold text-red-600" onClick={() => removeProjectListing(index)}>
                      Remove Project
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-slate-200 p-4 space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-bold uppercase tracking-wide">Skills & Achievements</h3>
                <button className="text-sm font-semibold text-indigo-700" onClick={addSkillListing}>
                  + Add Skill Row
                </button>
              </div>
              {resumeDraft.skills_achievements.listings.map((listing, index) => (
                <div key={listing.id} className="rounded-xl border border-slate-100 p-3 bg-slate-50 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <LabeledInput
                      label="ID"
                      value={listing.id}
                      onChange={(value) => handleSkillListingUpdate(index, "id", value)}
                    />
                    <LabeledInput
                      label="Category"
                      value={listing.category}
                      onChange={(value) => handleSkillListingUpdate(index, "category", value)}
                    />
                    <LabeledInput
                      label="Text"
                      value={listing.text}
                      onChange={(value) => handleSkillListingUpdate(index, "text", value)}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold">
                      <input
                        type="checkbox"
                        checked={listing.enabled}
                        onChange={(event) => handleSkillListingUpdate(index, "enabled", event.target.checked)}
                      />{" "}
                      Enabled
                    </label>
                    <button className="text-xs font-semibold text-red-600" onClick={() => removeSkillListing(index)}>
                      Remove Row
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end">
              <button
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleResumeGuidedSave}
                disabled={resumeStructuredMutation.isPending}
              >
                {resumeStructuredMutation.isPending ? "Saving..." : "Save Guided Resume"}
              </button>
            </div>
          </div>
        )}

        {resumeTab === "yaml" && (
          <div className="space-y-4">
            <YamlEditor modelPath={RESUME_EDITOR_MODEL_URI} value={resumeYamlDraft} onChange={setResumeYamlDraft} />
            <div className="flex justify-end">
              <button
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                style={{ backgroundColor: COLOR_PRIMARY }}
                onClick={handleResumeYamlSave}
                disabled={resumeYamlMutation.isPending}
              >
                {resumeYamlMutation.isPending ? "Saving..." : "Save YAML"}
              </button>
            </div>
          </div>
        )}

        {resumeTab === "tex" && (
          <div className="space-y-4">
            <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
              Upload a LaTeX resume source (`.tex`) and convert it into canonical YAML automatically.
            </p>
            <input
              ref={resumeTexInputRef}
              type="file"
              accept=".tex,text/plain"
              className="hidden"
              onChange={handleResumeTexUpload}
            />
            <button
              className="px-4 py-2 rounded-lg border border-slate-200 text-sm font-semibold"
              onClick={() => resumeTexInputRef.current?.click()}
              disabled={resumeTexMutation.isPending}
            >
              {resumeTexMutation.isPending ? "Converting..." : "Upload TeX and Convert"}
            </button>
            {lastResumeMigrationSummary !== null && (
              <p className="text-xs text-emerald-700">Latest migration: {lastResumeMigrationSummary}</p>
            )}
          </div>
        )}

        {resumeTab === "files" && (
          <div className="space-y-4">
            <SettingsFileCard
              title="Resume YAML"
              subtitle={resumeMetadata?.modified_at ? new Date(resumeMetadata.modified_at).toLocaleString() : "No file timestamp"}
              downloadUrl={getResumeDownloadUrl()}
            />
            <input
              ref={resumeYamlInputRef}
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              className="hidden"
              onChange={handleResumeYamlUpload}
            />
            <button
              className="px-4 py-2 rounded-lg border border-slate-200 text-sm font-semibold"
              onClick={() => resumeYamlInputRef.current?.click()}
              disabled={resumeUploadMutation.isPending}
            >
              {resumeUploadMutation.isPending ? "Uploading..." : "Replace Resume YAML"}
            </button>
          </div>
        )}
      </section>

      {hasAnyError && (
        <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
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

/** Props for settings section tab buttons. */
interface TabButtonProps {
  /** Whether the tab is currently active. */
  readonly active: boolean;
  /** Tab label text. */
  readonly label: string;
  /** Click handler for tab activation. */
  readonly onClick: () => void;
}

/**
 * Render one compact settings tab button.
 *
 * @param props - Tab button props.
 * @returns One tab button element.
 */
function TabButton({ active, label, onClick }: TabButtonProps): JSX.Element {
  return (
    <button
      className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
        active ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
      }`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/** Props for labeled single-line input. */
interface LabeledInputProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one labeled text input.
 *
 * @param props - Labeled input props.
 * @returns One input field block.
 */
function LabeledInput({ label, value, onChange }: LabeledInputProps): JSX.Element {
  return (
    <label className="text-xs font-semibold block">
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-sm"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </label>
  );
}

/** Props for labeled textarea input. */
interface LabeledTextareaProps {
  /** Field label text. */
  readonly label: string;
  /** Current field value. */
  readonly value: string;
  /** Callback for value changes. */
  readonly onChange: (value: string) => void;
  /** Optional row count override. */
  readonly rows?: number;
}

/**
 * Render one labeled textarea.
 *
 * @param props - Labeled textarea props.
 * @returns One textarea block.
 */
function LabeledTextarea({ label, value, onChange, rows = 5 }: LabeledTextareaProps): JSX.Element {
  return (
    <label className="text-xs font-semibold block">
      {label}
      <textarea
        className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 text-sm"
        rows={rows}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </label>
  );
}

/** Props for compact file metadata cards. */
interface SettingsFileCardProps {
  /** File card title. */
  readonly title: string;
  /** File metadata subtitle text. */
  readonly subtitle: string;
  /** Download URL for file action link. */
  readonly downloadUrl: string;
}

/**
 * Render one compact settings file metadata card.
 *
 * @param props - File card props.
 * @returns One file metadata card element.
 */
function SettingsFileCard({ title, subtitle, downloadUrl }: SettingsFileCardProps): JSX.Element {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 flex items-center justify-between">
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
      <a className="text-sm font-semibold text-indigo-700 hover:underline" href={downloadUrl} target="_blank" rel="noreferrer">
        Download
      </a>
    </div>
  );
}

/** Props for monaco-backed YAML editor wrapper. */
interface YamlEditorProps {
  /** Model URI path for schema matching. */
  readonly modelPath: string;
  /** Current editor value. */
  readonly value: string;
  /** Callback invoked on editor value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one Monaco YAML editor with schema tooling enabled.
 *
 * @param props - YAML editor props.
 * @returns One editor panel element.
 */
function YamlEditor({ modelPath, value, onChange }: YamlEditorProps): JSX.Element {
  function handleBeforeMount(monaco: Monaco): void {
    configureYamlSchemas(monaco);
  }

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <Editor
        beforeMount={handleBeforeMount}
        path={modelPath}
        defaultLanguage="yaml"
        height={`${EDITOR_HEIGHT_PX}px`}
        value={value}
        onChange={(nextValue) => {
          onChange(nextValue ?? "");
        }}
        options={{
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          wordWrap: "on",
          automaticLayout: true,
        }}
      />
    </div>
  );
}
