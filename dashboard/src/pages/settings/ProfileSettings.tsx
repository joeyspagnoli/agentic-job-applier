/**
 * @packageDocumentation
 *
 * Candidate profile section orchestrator. Owns the profile query, mutations,
 * and draft state, and routes between the guided / YAML / files sub-tabs.
 */

import type { ChangeEvent, JSX } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchProfileSettings,
  fetchSettingsFiles,
  getProfileDownloadUrl,
  updateProfileStructured,
  updateProfileYaml,
  uploadProfile,
} from "@/lib/api/client";
import { PROFILE_EDITOR_MODEL_URI } from "@/lib/monaco/yaml-config";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";
import { getErrorMessage, toProfileDraft } from "@/lib/settings/transforms";
import type { ProfileDraft } from "@/lib/settings/transforms";
import type { CandidateTab } from "@/lib/settings/types";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { SettingsFileCard } from "@/components/settings/SettingsFileCard";
import { TabButton } from "@/components/settings/TabButton";
import { YamlEditor } from "@/components/settings/YamlEditor";
import { ProfileGuidedView } from "./ProfileGuidedView";

/** Props for the candidate profile section. */
export interface ProfileSettingsProps {
  /** Callback invoked whenever the dirty flag changes. */
  readonly onDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked whenever the section error state changes. */
  readonly onErrorChange: (hasError: boolean) => void;
}

/**
 * Render the candidate profile editor section.
 *
 * @param props - Section props.
 * @returns Profile editor section element.
 */
export function ProfileSettings({
  onDirtyChange,
  onErrorChange,
}: ProfileSettingsProps): JSX.Element {
  const queryClient = useQueryClient();
  const profileYamlInputRef = useRef<HTMLInputElement | null>(null);

  const [candidateTab, setCandidateTab] = useState<CandidateTab>("guided");
  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);
  const [profileYamlDraft, setProfileYamlDraft] = useState("");
  const [isProfileDirty, setIsProfileDirty] = useState(false);

  const profileQuery = useQuery({
    queryKey: ["settings", "profile"],
    queryFn: fetchProfileSettings,
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
    if (profileQuery.data !== undefined && !isProfileDirty) {
      setProfileDraft(toProfileDraft(profileQuery.data));
      setProfileYamlDraft(profileQuery.data.yaml_text);
    }
  }, [profileQuery.data, isProfileDirty]);

  useEffect(() => {
    onDirtyChange(isProfileDirty);
  }, [isProfileDirty, onDirtyChange]);

  const profileStructuredMutation = useMutation({
    mutationFn: updateProfileStructured,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileYamlMutation = useMutation({
    mutationFn: updateProfileYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "profile"], response);
      setProfileDraft(toProfileDraft(response));
      setProfileYamlDraft(response.yaml_text);
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  const profileUploadMutation = useMutation({
    mutationFn: uploadProfile,
    onSuccess: async () => {
      setIsProfileDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "profile"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "files"] });
    },
  });

  useEffect(() => {
    onErrorChange(
      profileQuery.isError ||
        filesQuery.isError ||
        profileStructuredMutation.isError ||
        profileYamlMutation.isError ||
        profileUploadMutation.isError,
    );
  }, [
    profileQuery.isError,
    filesQuery.isError,
    profileStructuredMutation.isError,
    profileYamlMutation.isError,
    profileUploadMutation.isError,
    onErrorChange,
  ]);

  const profileMetadata = profileQuery.data?.metadata ?? filesQuery.data?.profile;

  const handleProfileDraftChange = useCallback(
    (next: ProfileDraft | ((current: ProfileDraft) => ProfileDraft)): void => {
      setProfileDraft((currentDraft) => {
        if (currentDraft === null) {
          return currentDraft;
        }
        if (typeof next === "function") {
          return next(currentDraft);
        }
        return next;
      });
      setIsProfileDirty(true);
    },
    [],
  );

  function handleProfileYamlDraftChange(nextYaml: string): void {
    setProfileYamlDraft(nextYaml);
    setIsProfileDirty(true);
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

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Candidate Profile
          </h3>
          <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            This profile is always available and drives gate-agent decision quality.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TabButton
            active={candidateTab === "guided"}
            label="Guided"
            onClick={() => setCandidateTab("guided")}
          />
          <TabButton
            active={candidateTab === "yaml"}
            label="Advanced YAML"
            onClick={() => setCandidateTab("yaml")}
          />
          <TabButton
            active={candidateTab === "files"}
            label="File Actions"
            onClick={() => setCandidateTab("files")}
          />
        </div>
      </div>

      {candidateTab === "guided" && profileDraft !== null && (
        <ProfileGuidedView
          profileDraft={profileDraft}
          onDraftChange={handleProfileDraftChange}
          isPending={profileStructuredMutation.isPending}
          isDirty={isProfileDirty}
          isError={profileStructuredMutation.isError}
          errorMessage={profileStructuredMutation.error}
          onSave={handleProfileGuidedSave}
        />
      )}

      {candidateTab === "yaml" && (
        <div className="space-y-4">
          <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
            Advanced: editing YAML here overrides guided form values.
          </p>
          <YamlEditor
            modelPath={PROFILE_EDITOR_MODEL_URI}
            value={profileYamlDraft}
            onChange={handleProfileYamlDraftChange}
          />
          <div className="flex justify-end">
            <button
              className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={handleProfileYamlSave}
              disabled={profileYamlMutation.isPending || !isProfileDirty}
            >
              {profileYamlMutation.isPending ? "Saving..." : "Save YAML"}
            </button>
          </div>
          {profileYamlMutation.isError && (
            <InlineErrorText
              message={`YAML save failed: ${getErrorMessage(profileYamlMutation.error)}`}
            />
          )}
        </div>
      )}

      {candidateTab === "files" && (
        <div className="space-y-4">
          <SettingsFileCard
            title="Candidate Profile YAML"
            subtitle={
              profileMetadata?.modified_at
                ? new Date(profileMetadata.modified_at).toLocaleString()
                : "No file timestamp"
            }
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
            className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
            onClick={() => profileYamlInputRef.current?.click()}
            disabled={profileUploadMutation.isPending}
          >
            {profileUploadMutation.isPending ? "Uploading..." : "Replace Profile YAML"}
          </button>
          {profileUploadMutation.isError && (
            <InlineErrorText
              message={`Upload failed: ${getErrorMessage(profileUploadMutation.error)}`}
            />
          )}
        </div>
      )}
    </section>
  );
}
