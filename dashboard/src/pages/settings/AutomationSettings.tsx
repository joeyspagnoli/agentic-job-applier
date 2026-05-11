/**
 * @packageDocumentation
 *
 * Automation card for the General settings tab. Lets the user pick the
 * per-stage automation mode (autonomous / opt-in / both) for the tailor
 * and review stages. Writes back through
 * `PATCH /api/system-settings/automation` so the worker observes the
 * change on its next poll cycle.
 */

import type { JSX } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAutomationSettings,
  patchAutomationSettings,
} from "@/lib/api/client";
import type { AutomationMode } from "@/lib/api/types";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE_VARIANT,
} from "@/lib/design-tokens";

/** One automation-mode radio option. */
interface ModeOption {
  readonly value: AutomationMode;
  readonly label: string;
  readonly description: string;
}

const MODE_OPTIONS: readonly ModeOption[] = [
  {
    value: "autonomous",
    label: "Autonomous",
    description: "The worker claims and processes jobs without user input.",
  },
  {
    value: "opt_in",
    label: "Opt-in",
    description: "Only runs the user triggers from the dashboard.",
  },
  {
    value: "both",
    label: "Both",
    description: "Autonomous runs for unclaimed jobs; user-triggered runs preempt.",
  },
];

/** Props for the Automation card. */
export interface AutomationSettingsProps {
  /** Callback invoked when the patch mutation succeeds or fails. */
  readonly onErrorChange?: (hasError: boolean) => void;
}

/**
 * Render the Automation card.
 *
 * @param props - Section props.
 * @returns The Automation card element.
 */
export function AutomationSettings({
  onErrorChange,
}: AutomationSettingsProps = {}): JSX.Element {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["automation-settings"],
    queryFn: fetchAutomationSettings,
  });

  const mutation = useMutation({
    mutationFn: patchAutomationSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["automation-settings"] });
      if (onErrorChange) {
        onErrorChange(false);
      }
    },
    onError: () => {
      if (onErrorChange) {
        onErrorChange(true);
      }
    },
  });

  const tailorMode = query.data?.tailor_mode ?? "opt_in";
  const reviewMode = query.data?.review_mode ?? "opt_in";

  return (
    <section
      className="rounded-2xl border p-6 space-y-5"
      style={{
        borderColor: `${COLOR_OUTLINE_VARIANT}40`,
      }}
    >
      <header>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Automation
        </h2>
        <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Decide whether each stage runs autonomously, on-demand, or both.
          Changes take effect on the worker's next poll cycle.
        </p>
      </header>

      <ModeRadioGroup
        title="Resume tailor"
        currentValue={tailorMode}
        disabled={mutation.isPending || query.isLoading}
        onChange={(value) => mutation.mutate({ tailor_mode: value })}
      />

      <ModeRadioGroup
        title="Resume review"
        currentValue={reviewMode}
        disabled={mutation.isPending || query.isLoading}
        onChange={(value) => mutation.mutate({ review_mode: value })}
      />

      {mutation.error ? (
        <p className="text-xs" style={{ color: "#b91c1c" }}>
          Save failed: {(mutation.error as Error).message}
        </p>
      ) : null}
    </section>
  );
}

/** Props for the inner radio group rendering one stage's mode picker. */
interface ModeRadioGroupProps {
  readonly title: string;
  readonly currentValue: AutomationMode;
  readonly disabled: boolean;
  readonly onChange: (value: AutomationMode) => void;
}

/**
 * Render one stage's radio-group selector.
 *
 * @param props - {@link ModeRadioGroupProps}
 * @returns A labeled radio group covering the three automation modes.
 */
function ModeRadioGroup({
  title,
  currentValue,
  disabled,
  onChange,
}: ModeRadioGroupProps): JSX.Element {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE }}>
        {title}
      </legend>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {MODE_OPTIONS.map((option) => {
          const isSelected = option.value === currentValue;
          return (
            <label
              key={option.value}
              className="flex items-start gap-2 rounded-xl border px-3 py-2 cursor-pointer"
              style={{
                borderColor: isSelected
                  ? "var(--color-primary, #2563eb)"
                  : `${COLOR_OUTLINE_VARIANT}60`,
                opacity: disabled ? 0.7 : 1,
              }}
            >
              <input
                type="radio"
                name={title}
                value={option.value}
                checked={isSelected}
                disabled={disabled}
                onChange={() => onChange(option.value)}
                className="mt-1"
              />
              <span>
                <span
                  className="block text-sm font-semibold"
                  style={{ color: COLOR_ON_SURFACE }}
                >
                  {option.label}
                </span>
                <span
                  className="block text-xs"
                  style={{ color: COLOR_ON_SURFACE_VARIANT }}
                >
                  {option.description}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
