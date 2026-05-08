/**
 * @packageDocumentation
 *
 * Step 1 of the onboarding wizard: basic candidate profile information.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
import type { ProfileDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepProfile}. */
export interface StepProfileProps {
  /** Current profile draft. */
  readonly draft: ProfileDraft;
  /** Replace the draft with `next`. */
  readonly onChange: (next: ProfileDraft) => void;
}

/**
 * Step 1: Basic profile information.
 *
 * @param props - {@link StepProfileProps}
 * @returns Profile form fields.
 */
export function StepProfile({ draft, onChange }: StepProfileProps): JSX.Element {
  /**
   * Update a single profile field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof ProfileDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          About You
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Basic contact information for your applications.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Full Name"
          value={draft.fullName}
          onChange={(v) => {
            set("fullName", v);
          }}
          placeholder="Jane Doe"
          required
        />
        <Field
          label="Email"
          value={draft.email}
          onChange={(v) => {
            set("email", v);
          }}
          placeholder="jane@example.com"
          type="email"
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="Phone"
          value={draft.phone}
          onChange={(v) => {
            set("phone", v);
          }}
          placeholder="+1 555-0123"
        />
        <Field
          label="City"
          value={draft.city}
          onChange={(v) => {
            set("city", v);
          }}
          placeholder="San Francisco"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field
          label="State / Region"
          value={draft.stateOrRegion}
          onChange={(v) => {
            set("stateOrRegion", v);
          }}
          placeholder="California"
        />
        <Field
          label="Country Code"
          value={draft.countryCode}
          onChange={(v) => {
            set("countryCode", v);
          }}
          placeholder="US"
        />
      </div>
      <Field
        label="LinkedIn URL"
        value={draft.linkedinUrl}
        onChange={(v) => {
          set("linkedinUrl", v);
        }}
        placeholder="https://linkedin.com/in/..."
      />
      <Field
        label="Professional Summary"
        value={draft.summary}
        onChange={(v) => {
          set("summary", v);
        }}
        placeholder="Brief overview of your experience and goals..."
        multiline
      />
    </div>
  );
}
