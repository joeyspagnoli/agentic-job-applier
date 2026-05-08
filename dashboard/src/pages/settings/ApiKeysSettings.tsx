/**
 * @packageDocumentation
 *
 * API keys section of the General settings tab. Allows write-only management
 * of provider/service keys plus inline feedback on save and delete.
 */

import type { JSX } from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteApiKeySetting,
  fetchApiKeysSettings,
  upsertApiKeySetting,
} from "@/lib/api/client";
import type { ApiKeyNameDto } from "@/lib/api/types";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_ON_WARNING_CONTAINER,
  COLOR_SUCCESS,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { API_KEYS } from "@/lib/settings/constants";
import { getErrorMessage } from "@/lib/settings/transforms";
import type { FeedbackMessage } from "@/lib/settings/types";
import { InlineErrorText } from "@/components/settings/InlineErrorText";
import { ApiKeyRow } from "./ApiKeyRow";

/** Props for the API keys settings section. */
export interface ApiKeysSettingsProps {
  /** Callback invoked when the section dirty flag changes. */
  readonly onDirtyChange: (isDirty: boolean) => void;
}

/**
 * Render the API keys settings section.
 *
 * @param props - Section props.
 * @returns API keys section element.
 */
export function ApiKeysSettings({ onDirtyChange }: ApiKeysSettingsProps): JSX.Element {
  const queryClient = useQueryClient();
  const [editingApiKeyName, setEditingApiKeyName] = useState<ApiKeyNameDto | null>(null);
  const [editingApiKeyValue, setEditingApiKeyValue] = useState("");
  const [apiKeyFeedback, setApiKeyFeedback] = useState<FeedbackMessage | null>(null);

  const apiKeysQuery = useQuery({
    queryKey: ["settings", "api-keys"],
    queryFn: fetchApiKeysSettings,
    retry: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    onDirtyChange(editingApiKeyName !== null);
  }, [editingApiKeyName, onDirtyChange]);

  useEffect(() => {
    if (apiKeyFeedback === null) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setApiKeyFeedback(null);
    }, 3000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [apiKeyFeedback]);

  const apiKeyUpsertMutation = useMutation({
    mutationFn: (payload: { keyName: ApiKeyNameDto; keyValue: string }) =>
      upsertApiKeySetting(payload.keyName, payload.keyValue),
    onSuccess: async (response, payload) => {
      queryClient.setQueryData(["settings", "api-keys"], response);
      setEditingApiKeyName(null);
      setEditingApiKeyValue("");
      setApiKeyFeedback({ type: "success", message: `${payload.keyName} saved.` });
      await queryClient.invalidateQueries({ queryKey: ["settings", "api-keys"] });
    },
    onError: (error, payload) => {
      setApiKeyFeedback({
        type: "error",
        message: `Failed to save ${payload.keyName}: ${getErrorMessage(error)}`,
      });
    },
  });

  const apiKeyDeleteMutation = useMutation({
    mutationFn: (keyName: ApiKeyNameDto) => deleteApiKeySetting(keyName),
    onSuccess: async (response, keyName) => {
      queryClient.setQueryData(["settings", "api-keys"], response);
      if (editingApiKeyName === keyName) {
        setEditingApiKeyName(null);
        setEditingApiKeyValue("");
      }
      setApiKeyFeedback({ type: "success", message: `${keyName} removed.` });
      await queryClient.invalidateQueries({ queryKey: ["settings", "api-keys"] });
    },
    onError: (error, keyName) => {
      setApiKeyFeedback({
        type: "error",
        message: `Failed to remove ${keyName}: ${getErrorMessage(error)}`,
      });
    },
  });

  const normalizedApiKeys = useMemo(
    () =>
      API_KEYS.map((apiKey) => ({
        name: apiKey.name,
        configured:
          apiKeysQuery.data?.keys.find((responseKey) => responseKey.name === apiKey.name)
            ?.configured ?? false,
      })),
    [apiKeysQuery.data],
  );

  function startApiKeyEdit(keyName: ApiKeyNameDto): void {
    setEditingApiKeyName(keyName);
    setEditingApiKeyValue("");
    setApiKeyFeedback(null);
  }

  function cancelApiKeyEdit(): void {
    setEditingApiKeyName(null);
    setEditingApiKeyValue("");
  }

  function handleApiKeySave(keyName: ApiKeyNameDto): void {
    if (editingApiKeyValue.trim() === "") {
      setApiKeyFeedback({ type: "error", message: `${keyName} cannot be empty.` });
      return;
    }
    apiKeyUpsertMutation.mutate({ keyName, keyValue: editingApiKeyValue.trim() });
  }

  function handleApiKeyDelete(keyName: ApiKeyNameDto): void {
    if (!window.confirm(`Delete ${keyName}? This action cannot be undone.`)) {
      return;
    }
    apiKeyDeleteMutation.mutate(keyName);
  }

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div>
        <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
          API Keys
        </h3>
        <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Manage provider and service secrets. Keys are write-only and cannot be read after saving.
        </p>
      </div>

      {apiKeysQuery.isError && (
        <div
          className="rounded-xl border px-4 py-3 text-sm"
          style={{
            borderColor: COLOR_WARNING,
            color: COLOR_ON_WARNING_CONTAINER,
            backgroundColor: COLOR_WARNING_CONTAINER,
          }}
        >
          API key status endpoint is not available yet. UI is ready; backend wiring is still
          required.
        </div>
      )}

      <div className="space-y-3">
        {API_KEYS.map((apiKey) => {
          const isConfigured =
            normalizedApiKeys.find((entry) => entry.name === apiKey.name)?.configured ?? false;
          const isEditing = editingApiKeyName === apiKey.name;
          const isSavingThisKey =
            apiKeyUpsertMutation.isPending &&
            apiKeyUpsertMutation.variables?.keyName === apiKey.name;
          const isDeletingThisKey =
            apiKeyDeleteMutation.isPending && apiKeyDeleteMutation.variables === apiKey.name;

          return (
            <ApiKeyRow
              key={apiKey.name}
              name={apiKey.name}
              icon={apiKey.icon}
              description={apiKey.description}
              isConfigured={isConfigured}
              isEditing={isEditing}
              isSaving={isSavingThisKey}
              isDeleting={isDeletingThisKey}
              editingValue={isEditing ? editingApiKeyValue : ""}
              onStartEdit={() => startApiKeyEdit(apiKey.name)}
              onCancelEdit={cancelApiKeyEdit}
              onEditingValueChange={setEditingApiKeyValue}
              onSave={() => handleApiKeySave(apiKey.name)}
              onDelete={() => handleApiKeyDelete(apiKey.name)}
            />
          );
        })}
      </div>

      {apiKeyFeedback !== null && apiKeyFeedback.type === "success" && (
        <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
          {apiKeyFeedback.message}
        </p>
      )}
      {apiKeyFeedback !== null && apiKeyFeedback.type === "error" && (
        <InlineErrorText message={apiKeyFeedback.message} />
      )}
    </section>
  );
}
