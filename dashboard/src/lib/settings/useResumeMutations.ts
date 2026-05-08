/**
 * @packageDocumentation
 *
 * React hook bundling the resume queries and mutations used by
 * `ResumeSettings`. Keeps the orchestrator focused on rendering.
 */

import type { ChangeEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import {
  fetchResumeSettings,
  fetchServiceTierSetting,
  fetchSettingsFiles,
  updateResumeStructured,
  updateResumeYaml,
  uploadResume,
  uploadResumeTex,
} from "@/lib/api/client";
import type {
  ResumeContentDto,
  ServiceTierDto,
  SettingsFilesDto,
  SettingsResumeDto,
  SettingsResumeTexUploadDto,
  SettingsResumeUploadDto,
} from "@/lib/api/types";
import { toResumeDraft } from "./transforms";

/** Bundle of state, derived data, and handlers used by `ResumeSettings`. */
export interface ResumeSettingsState {
  /** Whether the active service tier permits resume editing. */
  readonly canOpenResumeEditor: boolean;
  /** The currently active service tier (defaults to base). */
  readonly serviceTier: ServiceTierDto;
  /** The structured resume draft (or `null` until first load). */
  readonly resumeDraft: ResumeContentDto | null;
  /** The raw YAML draft text. */
  readonly resumeYamlDraft: string;
  /** Whether either draft has unsaved changes. */
  readonly isResumeDirty: boolean;
  /** Latest TeX migration summary, or `null`. */
  readonly lastMigrationSummary: string | null;
  /** Pre-rendered counts text for the section header. */
  readonly resumeCountsText: string;
  /** Subtitle text for the file metadata card. */
  readonly fileSubtitle: string;
  /** Resume settings query result. */
  readonly resumeQuery: UseQueryResult<SettingsResumeDto>;
  /** Files settings query result. */
  readonly filesQuery: UseQueryResult<SettingsFilesDto>;
  /** Structured save mutation. */
  readonly resumeStructuredMutation: UseMutationResult<SettingsResumeDto, Error, ResumeContentDto>;
  /** Raw YAML save mutation. */
  readonly resumeYamlMutation: UseMutationResult<SettingsResumeDto, Error, string>;
  /** YAML upload mutation. */
  readonly resumeUploadMutation: UseMutationResult<SettingsResumeUploadDto, Error, File>;
  /** TeX-to-YAML conversion mutation. */
  readonly resumeTexMutation: UseMutationResult<SettingsResumeTexUploadDto, Error, File>;
  /** Replace the structured draft (functional updates accepted). */
  readonly handleResumeDraftChange: (
    next: ResumeContentDto | ((current: ResumeContentDto) => ResumeContentDto),
  ) => void;
  /** Replace the YAML draft text. */
  readonly handleResumeYamlDraftChange: (next: string) => void;
  /** Persist the structured draft. */
  readonly handleResumeGuidedSave: () => void;
  /** Persist the YAML draft text. */
  readonly handleResumeYamlSave: () => void;
  /** Handler for the YAML file picker. */
  readonly handleResumeYamlUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  /** Handler for the TeX file picker. */
  readonly handleResumeTexUpload: (event: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Build the queries, mutations, and handlers used by `ResumeSettings`.
 *
 * @param onDirtyChange - Bubble dirty changes to the orchestrator's parent.
 * @param onErrorChange - Bubble error changes to the orchestrator's parent.
 * @returns State bundle for the resume settings section.
 */
export function useResumeMutations(
  onDirtyChange: (isDirty: boolean) => void,
  onErrorChange: (hasError: boolean) => void,
): ResumeSettingsState {
  const queryClient = useQueryClient();
  const [resumeDraft, setResumeDraft] = useState<ResumeContentDto | null>(null);
  const [resumeYamlDraft, setResumeYamlDraft] = useState("");
  const [isResumeDirty, setIsResumeDirty] = useState(false);
  const [lastMigrationSummary, setLastMigrationSummary] = useState<string | null>(null);

  const tierQuery = useQuery({
    queryKey: ["settings", "service-tier"],
    queryFn: fetchServiceTierSetting,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const serviceTier: ServiceTierDto = tierQuery.data?.tier ?? "base";
  const canOpenResumeEditor = serviceTier === "latex" || serviceTier === "full";

  const resumeQuery = useQuery({
    queryKey: ["settings", "resume"],
    queryFn: fetchResumeSettings,
    enabled: canOpenResumeEditor,
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
    if (resumeQuery.data !== undefined && !isResumeDirty) {
      setResumeDraft(toResumeDraft(resumeQuery.data));
      setResumeYamlDraft(resumeQuery.data.yaml_text);
    }
  }, [resumeQuery.data, isResumeDirty]);

  useEffect(() => {
    onDirtyChange(isResumeDirty);
  }, [isResumeDirty, onDirtyChange]);

  const resumeStructuredMutation = useMutation({
    mutationFn: updateResumeStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setIsResumeDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeYamlMutation = useMutation({
    mutationFn: updateResumeYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "resume"], response);
      setResumeDraft(toResumeDraft(response));
      setResumeYamlDraft(response.yaml_text);
      setIsResumeDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const resumeUploadMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: async () => {
      setIsResumeDirty(false);
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
      setIsResumeDirty(false);
      setLastMigrationSummary(
        `${response.migration.experience_listings} experience listings, ` +
          `${response.migration.project_listings} project listings, ` +
          `${response.migration.skill_rows} skills rows`,
      );
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  useEffect(() => {
    onErrorChange(
      canOpenResumeEditor &&
        (resumeQuery.isError ||
          resumeStructuredMutation.isError ||
          resumeYamlMutation.isError ||
          resumeUploadMutation.isError ||
          resumeTexMutation.isError),
    );
  }, [
    canOpenResumeEditor,
    resumeQuery.isError,
    resumeStructuredMutation.isError,
    resumeYamlMutation.isError,
    resumeUploadMutation.isError,
    resumeTexMutation.isError,
    onErrorChange,
  ]);

  const resumeMetadata = resumeQuery.data?.metadata ?? filesQuery.data?.resume;

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

  const fileSubtitle = resumeMetadata?.modified_at
    ? new Date(resumeMetadata.modified_at).toLocaleString()
    : "No file timestamp";

  const handleResumeDraftChange = useCallback(
    (next: ResumeContentDto | ((current: ResumeContentDto) => ResumeContentDto)): void => {
      setResumeDraft((currentDraft) => {
        if (currentDraft === null) {
          return currentDraft;
        }
        if (typeof next === "function") {
          return next(currentDraft);
        }
        return next;
      });
      setIsResumeDirty(true);
    },
    [],
  );

  const handleResumeYamlDraftChange = useCallback((nextYaml: string): void => {
    setResumeYamlDraft(nextYaml);
    setIsResumeDirty(true);
  }, []);

  const handleResumeGuidedSave = useCallback((): void => {
    if (resumeDraft === null) {
      return;
    }
    resumeStructuredMutation.mutate(resumeDraft);
  }, [resumeDraft, resumeStructuredMutation]);

  const handleResumeYamlSave = useCallback((): void => {
    resumeYamlMutation.mutate(resumeYamlDraft);
  }, [resumeYamlDraft, resumeYamlMutation]);

  const handleResumeYamlUpload = useCallback(
    (event: ChangeEvent<HTMLInputElement>): void => {
      const selectedFile = event.target.files?.[0];
      if (selectedFile === undefined) {
        return;
      }
      resumeUploadMutation.mutate(selectedFile);
      event.target.value = "";
    },
    [resumeUploadMutation],
  );

  const handleResumeTexUpload = useCallback(
    (event: ChangeEvent<HTMLInputElement>): void => {
      const selectedFile = event.target.files?.[0];
      if (selectedFile === undefined) {
        return;
      }
      resumeTexMutation.mutate(selectedFile);
      event.target.value = "";
    },
    [resumeTexMutation],
  );

  return {
    canOpenResumeEditor,
    serviceTier,
    resumeDraft,
    resumeYamlDraft,
    isResumeDirty,
    lastMigrationSummary,
    resumeCountsText,
    fileSubtitle,
    resumeQuery,
    filesQuery,
    resumeStructuredMutation,
    resumeYamlMutation,
    resumeUploadMutation,
    resumeTexMutation,
    handleResumeDraftChange,
    handleResumeYamlDraftChange,
    handleResumeGuidedSave,
    handleResumeYamlSave,
    handleResumeYamlUpload,
    handleResumeTexUpload,
  };
}
