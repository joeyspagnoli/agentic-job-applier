/**
 * @packageDocumentation
 *
 * Service tier section of the General settings tab. Lets the user pick
 * Base/LaTeX/Full and persists the choice once required keys are present.
 */

import type { JSX } from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchApiKeysSettings,
  fetchServiceTierSetting,
  updateServiceTierSetting,
} from "@/lib/api/client";
import type { ServiceTierDto } from "@/lib/api/types";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_ON_WARNING_CONTAINER,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SUCCESS,
  COLOR_WARNING,
  COLOR_WARNING_CONTAINER,
} from "@/lib/design-tokens";
import { API_KEYS, SERVICE_TIER_CARDS } from "@/lib/settings/constants";
import {
  buildConfiguredKeyMap,
  getErrorMessage,
  getMissingKeysForTier,
} from "@/lib/settings/transforms";
import type { FeedbackMessage } from "@/lib/settings/types";
import { InlineErrorText } from "@/components/settings/InlineErrorText";

/** Props for the service tier settings section. */
export interface ServiceTierSettingsProps {
  /** Callback invoked whenever the dirty flag changes. */
  readonly onDirtyChange: (isDirty: boolean) => void;
}

/**
 * Render the service tier settings section.
 *
 * @param props - Section props.
 * @returns Service tier section element.
 */
export function ServiceTierSettings({ onDirtyChange }: ServiceTierSettingsProps): JSX.Element {
  const queryClient = useQueryClient();
  const [selectedServiceTier, setSelectedServiceTier] = useState<ServiceTierDto>("base");
  const [isTierDirty, setIsTierDirty] = useState(false);
  const [tierFeedback, setTierFeedback] = useState<FeedbackMessage | null>(null);

  const apiKeysQuery = useQuery({
    queryKey: ["settings", "api-keys"],
    queryFn: fetchApiKeysSettings,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const tierQuery = useQuery({
    queryKey: ["settings", "service-tier"],
    queryFn: fetchServiceTierSetting,
    retry: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (tierQuery.data !== undefined && !isTierDirty) {
      setSelectedServiceTier(tierQuery.data.tier);
    }
  }, [tierQuery.data, isTierDirty]);

  useEffect(() => {
    onDirtyChange(isTierDirty);
  }, [isTierDirty, onDirtyChange]);

  useEffect(() => {
    if (tierFeedback === null) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setTierFeedback(null);
    }, 3000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [tierFeedback]);

  const tierMutation = useMutation({
    mutationFn: updateServiceTierSetting,
    onSuccess: async (response) => {
      queryClient.setQueryData(["settings", "service-tier"], response);
      setSelectedServiceTier(response.tier);
      setIsTierDirty(false);
      setTierFeedback({
        type: "success",
        message: `Service tier saved as ${response.tier.toUpperCase()}.`,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "service-tier"] });
    },
    onError: (error) => {
      setTierFeedback({
        type: "error",
        message: `Failed to save service tier: ${getErrorMessage(error)}`,
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
  const configuredApiKeyMap = useMemo(
    () => buildConfiguredKeyMap(normalizedApiKeys),
    [normalizedApiKeys],
  );
  const selectedTierMissingKeys = useMemo(
    () => getMissingKeysForTier(selectedServiceTier, configuredApiKeyMap),
    [configuredApiKeyMap, selectedServiceTier],
  );

  function handleServiceTierSelection(nextTier: ServiceTierDto): void {
    const missingKeys = getMissingKeysForTier(nextTier, configuredApiKeyMap);
    if (nextTier !== "base" && missingKeys.length > 0) {
      setTierFeedback({
        type: "error",
        message: `Cannot select ${nextTier.toUpperCase()}. Missing: ${missingKeys.join(", ")}.`,
      });
      return;
    }
    setSelectedServiceTier(nextTier);
    setIsTierDirty(true);
  }

  function handleServiceTierSave(): void {
    if (selectedServiceTier !== "base" && selectedTierMissingKeys.length > 0) {
      setTierFeedback({
        type: "error",
        message: `Cannot save ${selectedServiceTier.toUpperCase()}. Missing: ${selectedTierMissingKeys.join(", ")}.`,
      });
      return;
    }
    tierMutation.mutate(selectedServiceTier);
  }

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div>
        <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Service Tier
        </h3>
        <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Choose how much of the pipeline runs. Base includes discovery + gate logic and still works
          without provider keys.
        </p>
      </div>

      <div
        className="rounded-xl border px-4 py-3 text-sm"
        style={{
          borderColor: COLOR_WARNING,
          color: COLOR_ON_WARNING_CONTAINER,
          backgroundColor: COLOR_WARNING_CONTAINER,
        }}
      >
        Changing tiers requires restarting Docker Compose services. Check the deployment README for
        restart steps.
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {SERVICE_TIER_CARDS.map((tierCard) => {
          const missingKeys = getMissingKeysForTier(tierCard.tier, configuredApiKeyMap);
          const isBlocked = tierCard.tier !== "base" && missingKeys.length > 0;
          const isSelected = selectedServiceTier === tierCard.tier;
          return (
            <button
              key={tierCard.tier}
              type="button"
              className="rounded-xl border p-4 text-left space-y-3 transition-colors disabled:opacity-70"
              style={{
                borderColor: isSelected ? COLOR_PRIMARY : `${COLOR_OUTLINE_VARIANT}80`,
                borderWidth: isSelected ? 2 : 1,
                backgroundColor: isSelected ? COLOR_PRIMARY_FIXED : "#ffffff",
              }}
              onClick={() => {
                handleServiceTierSelection(tierCard.tier);
              }}
              disabled={isBlocked || tierMutation.isPending}
              title={isBlocked ? `Missing required keys: ${missingKeys.join(", ")}` : undefined}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className="material-symbols-outlined text-base"
                    style={{ color: COLOR_PRIMARY }}
                  >
                    {tierCard.icon}
                  </span>
                  <p className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
                    {tierCard.title}
                  </p>
                </div>
                {tierCard.badge !== undefined && (
                  <span
                    className="rounded-full px-2 py-1 text-[10px] font-bold text-white"
                    style={{ backgroundColor: COLOR_PRIMARY }}
                  >
                    {tierCard.badge}
                  </span>
                )}
              </div>

              <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
                {tierCard.description}
              </p>

              <ul className="space-y-1">
                {tierCard.features.map((feature) => (
                  <li
                    key={`${tierCard.tier}-${feature}`}
                    className="text-xs"
                    style={{ color: COLOR_ON_SURFACE_VARIANT }}
                  >
                    ✓ {feature}
                  </li>
                ))}
              </ul>

              {isBlocked && (
                <p className="text-xs font-semibold" style={{ color: COLOR_ERROR }}>
                  Missing keys: {missingKeys.join(", ")}
                </p>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex justify-end">
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={handleServiceTierSave}
          disabled={
            !isTierDirty ||
            tierMutation.isPending ||
            (selectedServiceTier !== "base" && selectedTierMissingKeys.length > 0)
          }
        >
          {tierMutation.isPending ? "Saving..." : "Save Tier"}
        </button>
      </div>

      {tierFeedback !== null && tierFeedback.type === "success" && (
        <p className="text-sm" style={{ color: COLOR_SUCCESS }}>
          {tierFeedback.message}
        </p>
      )}
      {tierFeedback !== null && tierFeedback.type === "error" && (
        <InlineErrorText message={tierFeedback.message} />
      )}
    </section>
  );
}
