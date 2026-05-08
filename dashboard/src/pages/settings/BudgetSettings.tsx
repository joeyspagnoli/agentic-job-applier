/**
 * @packageDocumentation
 *
 * Budget section of the General settings tab. Displays the monthly cap, spent
 * and remaining figures, and a save action that persists to the backend.
 */

import type { JSX } from "react";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatUsd } from "@/lib/api/adapters";
import { fetchBudget, updateBudget } from "@/lib/api/client";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";
import { getErrorMessage } from "@/lib/settings/transforms";
import { InlineErrorText } from "@/components/settings/InlineErrorText";

/** Props for the budget settings section. */
export interface BudgetSettingsProps {
  /** Callback invoked whenever the dirty flag changes. */
  readonly onDirtyChange: (isDirty: boolean) => void;
  /** Callback invoked when the section error state changes. */
  readonly onErrorChange: (hasError: boolean) => void;
}

/**
 * Render the monthly-budget settings section.
 *
 * @param props - Section props.
 * @returns Budget section element.
 */
export function BudgetSettings({ onDirtyChange, onErrorChange }: BudgetSettingsProps): JSX.Element {
  const queryClient = useQueryClient();
  const [budgetInput, setBudgetInput] = useState("0.00");
  const [isBudgetDirty, setIsBudgetDirty] = useState(false);

  const budgetQuery = useQuery({
    queryKey: ["budget"],
    queryFn: fetchBudget,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (budgetQuery.data !== undefined && !isBudgetDirty) {
      setBudgetInput(budgetQuery.data.monthly_budget_usd.toFixed(2));
    }
  }, [budgetQuery.data, isBudgetDirty]);

  useEffect(() => {
    onDirtyChange(isBudgetDirty);
  }, [isBudgetDirty, onDirtyChange]);

  const budgetMutation = useMutation({
    mutationFn: updateBudget,
    onSuccess: async (response) => {
      queryClient.setQueryData(["budget"], response);
      setBudgetInput(response.monthly_budget_usd.toFixed(2));
      setIsBudgetDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  useEffect(() => {
    onErrorChange(budgetQuery.isError || budgetMutation.isError);
  }, [budgetQuery.isError, budgetMutation.isError, onErrorChange]);

  const budgetUsedPct = Math.max(
    0,
    Math.min(100, Math.round(budgetQuery.data?.utilization_pct ?? 0)),
  );
  const budgetProgressColor = budgetUsedPct >= 100 ? COLOR_ERROR : COLOR_PRIMARY;
  const parsedBudgetInput = Number.parseFloat(budgetInput);
  const isBudgetInputValid = Number.isFinite(parsedBudgetInput) && parsedBudgetInput >= 0;

  function handleBudgetSave(): void {
    if (!Number.isFinite(parsedBudgetInput) || parsedBudgetInput < 0) {
      return;
    }
    budgetMutation.mutate(parsedBudgetInput);
  }

  return (
    <section className="rounded-2xl border border-outline-variant/30 bg-white p-6 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Monthly Budget
          </h3>
          <p className="text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
            Set a monthly spend cap for all automation-related API usage.
          </p>
        </div>
        <button
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: COLOR_PRIMARY }}
          onClick={handleBudgetSave}
          disabled={!isBudgetDirty || !isBudgetInputValid || budgetMutation.isPending}
        >
          {budgetMutation.isPending ? "Saving..." : "Save Budget"}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
          <p
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Monthly Limit ($)
          </p>
          <input
            className="mt-1 w-full bg-transparent text-lg font-bold focus:outline-none"
            style={{ color: COLOR_ON_SURFACE }}
            type="number"
            min="0"
            step="0.01"
            value={budgetInput}
            onChange={(event) => {
              setBudgetInput(event.target.value);
              setIsBudgetDirty(true);
            }}
          />
        </div>
        <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
          <p
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Spent This Month
          </p>
          <p className="mt-1 text-lg font-bold">{formatUsd(budgetQuery.data?.spent_usd ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low px-4 py-3">
          <p
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Remaining
          </p>
          <p className="mt-1 text-lg font-bold">{formatUsd(budgetQuery.data?.remaining_usd ?? 0)}</p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="h-2 rounded-full bg-surface-container overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{ width: `${budgetUsedPct}%`, backgroundColor: budgetProgressColor }}
          />
        </div>
        <p className="text-right text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {budgetUsedPct}% consumed
        </p>
      </div>
      {budgetMutation.isError && (
        <InlineErrorText message={`Budget save failed: ${getErrorMessage(budgetMutation.error)}`} />
      )}
    </section>
  );
}
