/**
 * @packageDocumentation
 *
 * Step 2 of the onboarding wizard: target roles, strongest areas, and
 * job-board search terms.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
import type { RolesDraft } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepRoles}. */
export interface StepRolesProps {
  /** Current roles draft. */
  readonly draft: RolesDraft;
  /** Replace the draft with `next`. */
  readonly onChange: (next: RolesDraft) => void;
}

/**
 * Step 2: Target roles and search preferences.
 *
 * @param props - {@link StepRolesProps}
 * @returns Roles form fields.
 */
export function StepRoles({ draft, onChange }: StepRolesProps): JSX.Element {
  /**
   * Update a single roles field.
   *
   * @param key - Field name to update.
   * @param value - New field value.
   */
  function set(key: keyof RolesDraft, value: string): void {
    onChange({ ...draft, [key]: value });
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Target Roles
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          What positions are you looking for? One per line.
        </p>
      </div>
      <Field
        label="Target Roles"
        value={draft.targetRoles}
        onChange={(v) => {
          set("targetRoles", v);
        }}
        placeholder="Software Engineer&#10;Full Stack Developer&#10;Backend Engineer"
        multiline
        required
      />
      <Field
        label="Strongest Areas"
        value={draft.strongestAreas}
        onChange={(v) => {
          set("strongestAreas", v);
        }}
        placeholder="Python&#10;React&#10;System Design"
        multiline
      />
      <Field
        label="Resume Tailor Notes"
        value={draft.experienceHighlights}
        onChange={(v) => {
          set("experienceHighlights", v);
        }}
        placeholder={
          "Led K8s migration reducing cold-start 8s → 800ms\nOwned on-call for 5M evals/day Python + K8s pipeline\nReact dashboard used by 200+ internal analysts\nStripe intern: fraud scoring 50K tx/day, PCI-DSS exposure"
        }
        multiline
      />
      <Field
        label="Job Board Search Terms"
        value={draft.searchTerms}
        onChange={(v) => {
          set("searchTerms", v);
        }}
        placeholder="software engineer&#10;full stack developer&#10;python developer"
        multiline
      />
    </div>
  );
}
