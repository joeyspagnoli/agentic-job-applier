/**
 * @packageDocumentation
 *
 * One row in the API keys list. Renders the key icon, label, configured
 * state, and an inline editor for entering or replacing the secret value.
 */

import type { CSSProperties, JSX } from "react";
import type { ApiKeyNameDto } from "@/lib/api/types";
import {
  COLOR_ERROR,
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_PRIMARY,
} from "@/lib/design-tokens";

/** Props for one API key row. */
export interface ApiKeyRowProps {
  /** Backend identifier for the key. */
  readonly name: ApiKeyNameDto;
  /** Material symbol icon name. */
  readonly icon: string;
  /** Human-readable description of the key's role. */
  readonly description: string;
  /** Whether the key is configured on the backend. */
  readonly isConfigured: boolean;
  /** Whether this row is currently in edit mode. */
  readonly isEditing: boolean;
  /** True while the upsert mutation is in flight for this key. */
  readonly isSaving: boolean;
  /** True while the delete mutation is in flight for this key. */
  readonly isDeleting: boolean;
  /** Current value of the inline secret input (empty when not editing). */
  readonly editingValue: string;
  /** Callback invoked when the user starts editing this key. */
  readonly onStartEdit: () => void;
  /** Callback invoked when the user cancels editing. */
  readonly onCancelEdit: () => void;
  /** Update the working secret value. */
  readonly onEditingValueChange: (value: string) => void;
  /** Persist the working secret value. */
  readonly onSave: () => void;
  /** Delete the persisted secret. */
  readonly onDelete: () => void;
}

/**
 * Render one API key row.
 *
 * @param props - Row props.
 * @returns API key row markup.
 */
export function ApiKeyRow({
  name,
  icon,
  description,
  isConfigured,
  isEditing,
  isSaving,
  isDeleting,
  editingValue,
  onStartEdit,
  onCancelEdit,
  onEditingValueChange,
  onSave,
  onDelete,
}: ApiKeyRowProps): JSX.Element {
  return (
    <div className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white border border-outline-variant/30">
            <span
              className="material-symbols-outlined text-base"
              style={{ color: COLOR_PRIMARY }}
            >
              {icon}
            </span>
          </div>
          <div>
            <p className="text-sm font-semibold" style={{ color: COLOR_ON_SURFACE }}>
              {name}
            </p>
            <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
              {isConfigured ? "● Configured" : "○ Not configured"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {!isConfigured && !isEditing && (
            <button
              className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={onStartEdit}
              disabled={isSaving || isDeleting}
            >
              Add Key
            </button>
          )}

          {isConfigured && !isEditing && (
            <>
              <button
                className="rounded-lg border border-outline-variant bg-white px-4 py-2 text-sm font-semibold"
                style={{ color: COLOR_ON_SURFACE_VARIANT }}
                onClick={onStartEdit}
                disabled={isSaving || isDeleting}
              >
                Update
              </button>
              <button
                className="text-sm font-semibold disabled:opacity-50"
                style={{ color: COLOR_ERROR }}
                onClick={onDelete}
                disabled={isDeleting || isSaving}
              >
                {isDeleting ? "Deleting..." : "Delete"}
              </button>
            </>
          )}
        </div>
      </div>

      <p className="text-xs" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
        {description}
      </p>

      {isEditing && (
        <div className="rounded-lg border border-outline-variant/40 bg-white p-3 space-y-3">
          <label
            className="block text-xs font-semibold"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Secret Value
            <input
              className="mt-2 w-full rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 text-sm"
              style={{ WebkitTextSecurity: "disc" } as CSSProperties}
              type="password"
              autoComplete="new-password"
              placeholder="sk-..."
              value={editingValue}
              onChange={(event) => {
                onEditingValueChange(event.target.value);
              }}
            />
          </label>
          <div className="flex items-center justify-end gap-3">
            <button
              className="rounded-lg px-3 py-2 text-sm font-semibold"
              style={{ color: COLOR_ON_SURFACE_VARIANT }}
              onClick={onCancelEdit}
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              style={{ backgroundColor: COLOR_PRIMARY }}
              onClick={onSave}
              disabled={isSaving || editingValue.trim() === ""}
            >
              {isSaving ? "Saving..." : "Save Key"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
