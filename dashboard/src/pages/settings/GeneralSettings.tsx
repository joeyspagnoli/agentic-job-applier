/**
 * @packageDocumentation
 *
 * Composer for the "General" top-level settings tab. Wraps Budget, API Keys,
 * and Service Tier sections.
 */

import type { JSX } from "react";
import { ApiKeysSettings } from "./ApiKeysSettings";
import { AutomationSettings } from "./AutomationSettings";
import { BudgetSettings } from "./BudgetSettings";

/** Props for the general settings tab. */
export interface GeneralSettingsProps {
  /** Callback for budget section dirty changes. */
  readonly onBudgetDirtyChange: (isDirty: boolean) => void;
  /** Callback for budget section error changes. */
  readonly onBudgetErrorChange: (hasError: boolean) => void;
  /** Callback for API keys section dirty changes. */
  readonly onApiKeysDirtyChange: (isDirty: boolean) => void;
}

/**
 * Render the General settings tab.
 *
 * @param props - Composer props.
 * @returns Stacked Budget + API Keys + Automation sections.
 */
export function GeneralSettings({
  onBudgetDirtyChange,
  onBudgetErrorChange,
  onApiKeysDirtyChange,
}: GeneralSettingsProps): JSX.Element {
  return (
    <>
      <BudgetSettings
        onDirtyChange={onBudgetDirtyChange}
        onErrorChange={onBudgetErrorChange}
      />
      <ApiKeysSettings onDirtyChange={onApiKeysDirtyChange} />
      <AutomationSettings />
    </>
  );
}
