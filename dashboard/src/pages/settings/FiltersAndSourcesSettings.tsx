/**
 * @packageDocumentation
 *
 * Composer for the Filters & Sources top-level tab. Owns draft state for the
 * three sub-tab views (guided, raw filters YAML, sources YAML) so drafts are
 * preserved as the user toggles between them.
 */

import type { JSX } from "react";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchFiltersSettings,
  fetchSourcesSettings,
  updateFiltersYaml,
  updateSourcesYaml,
} from "@/lib/api/client";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
import { CONFIRM_SWITCH_MESSAGE } from "@/lib/settings/constants";
import {
  getErrorMessage,
  parseFiltersGuidedDraft,
  serializeFiltersGuidedToYaml,
} from "@/lib/settings/transforms";
import type { FiltersGuidedDraft, FiltersTab } from "@/lib/settings/types";
import { TabButton } from "@/components/settings/TabButton";
import { FiltersGuidedSettings, FiltersYamlSettings } from "./FiltersSettings";
import { SourcesSettings } from "./SourcesSettings";

/** Props for the Filters & Sources composer. */
export interface FiltersAndSourcesSettingsProps {
  /** Callback invoked when any of the three sub-section dirty flags change. */
  readonly onDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked when the section error state changes. */
  readonly onErrorChange: (hasError: boolean) => void;
}

/**
 * Render the Filters & Sources tab.
 *
 * @param props - Composer props.
 * @returns Filters & Sources tab element.
 */
export function FiltersAndSourcesSettings({
  onDirtyChange,
  onErrorChange,
}: FiltersAndSourcesSettingsProps): JSX.Element {
  const queryClient = useQueryClient();

  const [activeFiltersTab, setActiveFiltersTab] = useState<FiltersTab>("guided");
  const [filtersGuidedDraft, setFiltersGuidedDraft] = useState<FiltersGuidedDraft | null>(null);
  const [filtersYamlDraft, setFiltersYamlDraft] = useState("");
  const [sourcesYamlDraft, setSourcesYamlDraft] = useState("");
  const [isFiltersGuidedDirty, setIsFiltersGuidedDirty] = useState(false);
  const [isFiltersDirty, setIsFiltersDirty] = useState(false);
  const [isSourcesDirty, setIsSourcesDirty] = useState(false);

  const filtersQuery = useQuery({
    queryKey: ["settings", "filters"],
    queryFn: fetchFiltersSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const sourcesQuery = useQuery({
    queryKey: ["settings", "sources"],
    queryFn: fetchSourcesSettings,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (filtersQuery.data !== undefined && !isFiltersDirty) {
      setFiltersYamlDraft(filtersQuery.data.yaml_text);
    }
    if (filtersQuery.data !== undefined && !isFiltersGuidedDirty) {
      setFiltersGuidedDraft(parseFiltersGuidedDraft(filtersQuery.data.data));
    }
  }, [filtersQuery.data, isFiltersDirty, isFiltersGuidedDirty]);

  useEffect(() => {
    if (sourcesQuery.data !== undefined && !isSourcesDirty) {
      setSourcesYamlDraft(sourcesQuery.data.yaml_text);
    }
  }, [sourcesQuery.data, isSourcesDirty]);

  const filtersYamlMutation = useMutation({
    mutationFn: updateFiltersYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "filters"], response);
      setFiltersYamlDraft(response.yaml_text);
      setFiltersGuidedDraft(parseFiltersGuidedDraft(response.data));
      setIsFiltersDirty(false);
      setIsFiltersGuidedDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "filters"] });
    },
  });

  const sourcesYamlMutation = useMutation({
    mutationFn: updateSourcesYaml,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "sources"], response);
      setSourcesYamlDraft(response.yaml_text);
      setIsSourcesDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["settings", "sources"] });
    },
  });

  useEffect(() => {
    onDirtyChange(isFiltersGuidedDirty || isFiltersDirty || isSourcesDirty);
  }, [isFiltersGuidedDirty, isFiltersDirty, isSourcesDirty, onDirtyChange]);

  useEffect(() => {
    onErrorChange(
      filtersQuery.isError ||
        sourcesQuery.isError ||
        filtersYamlMutation.isError ||
        sourcesYamlMutation.isError,
    );
  }, [
    filtersQuery.isError,
    sourcesQuery.isError,
    filtersYamlMutation.isError,
    sourcesYamlMutation.isError,
    onErrorChange,
  ]);

  function handleFiltersTabChange(nextTab: FiltersTab): void {
    if (nextTab === activeFiltersTab) {
      return;
    }
    const hasCurrentTabUnsavedChanges =
      (activeFiltersTab === "guided" && isFiltersGuidedDirty) ||
      (activeFiltersTab === "filters" && isFiltersDirty) ||
      (activeFiltersTab === "sources" && isSourcesDirty);
    if (hasCurrentTabUnsavedChanges && !window.confirm(CONFIRM_SWITCH_MESSAGE)) {
      return;
    }
    setActiveFiltersTab(nextTab);
  }

  function handleGuidedDraftChange(nextDraft: FiltersGuidedDraft): void {
    setFiltersGuidedDraft(nextDraft);
    setIsFiltersGuidedDirty(true);
  }

  function handleGuidedSave(): void {
    if (filtersGuidedDraft === null) {
      return;
    }
    const yamlText = serializeFiltersGuidedToYaml(filtersGuidedDraft);
    filtersYamlMutation.mutate(yamlText);
  }

  function handleFiltersYamlDraftChange(nextValue: string): void {
    setFiltersYamlDraft(nextValue);
    setIsFiltersDirty(true);
  }

  function handleFiltersYamlSave(): void {
    filtersYamlMutation.mutate(filtersYamlDraft);
  }

  function handleSourcesDraftChange(nextValue: string): void {
    setSourcesYamlDraft(nextValue);
    setIsSourcesDirty(true);
  }

  function handleSourcesSave(): void {
    sourcesYamlMutation.mutate(sourcesYamlDraft);
  }

  const filtersSaveErrorMessage = filtersYamlMutation.isError
    ? getErrorMessage(filtersYamlMutation.error)
    : null;
  const sourcesSaveErrorMessage = sourcesYamlMutation.isError
    ? getErrorMessage(sourcesYamlMutation.error)
    : null;

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Company & Job Filters
          </h3>
          <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Configure filtering rules and discovery source lists used by the ingestion pipeline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TabButton
            active={activeFiltersTab === "guided"}
            label="Guided"
            onClick={() => handleFiltersTabChange("guided")}
          />
          <TabButton
            active={activeFiltersTab === "filters"}
            label="Advanced YAML"
            onClick={() => handleFiltersTabChange("filters")}
          />
          <TabButton
            active={activeFiltersTab === "sources"}
            label="Company Sources"
            onClick={() => handleFiltersTabChange("sources")}
          />
        </div>
      </div>

      {activeFiltersTab === "guided" && filtersGuidedDraft !== null && (
        <FiltersGuidedSettings
          draft={filtersGuidedDraft}
          isDirty={isFiltersGuidedDirty}
          isLoading={filtersQuery.isLoading}
          isQueryError={filtersQuery.isError}
          isSaving={filtersYamlMutation.isPending}
          saveErrorMessage={filtersSaveErrorMessage}
          onDraftChange={handleGuidedDraftChange}
          onSave={handleGuidedSave}
        />
      )}

      {activeFiltersTab === "filters" && (
        <FiltersYamlSettings
          draft={filtersYamlDraft}
          isDirty={isFiltersDirty}
          isLoading={filtersQuery.isLoading}
          isQueryError={filtersQuery.isError}
          isSaving={filtersYamlMutation.isPending}
          saveErrorMessage={filtersSaveErrorMessage}
          onDraftChange={handleFiltersYamlDraftChange}
          onSave={handleFiltersYamlSave}
        />
      )}

      {activeFiltersTab === "sources" && (
        <SourcesSettings
          draft={sourcesYamlDraft}
          isDirty={isSourcesDirty}
          isLoading={sourcesQuery.isLoading}
          isQueryError={sourcesQuery.isError}
          isSaving={sourcesYamlMutation.isPending}
          saveErrorMessage={sourcesSaveErrorMessage}
          onDraftChange={handleSourcesDraftChange}
          onSave={handleSourcesSave}
        />
      )}
    </section>
  );
}
