/**
 * @packageDocumentation
 *
 * Contact + Work Authorization sub-section of the guided profile editor.
 */

import type { JSX } from "react";
import type { SettingsProfileDto } from "@/lib/api/types";
import { buildPrioritizedCountryOptions } from "@/lib/constants/countries";
import { COLOR_ON_SURFACE, COLOR_OUTLINE } from "@/lib/design-tokens";
import { YES_NO_UNKNOWN_OPTIONS } from "@/lib/settings/constants";
import { LabeledInput } from "@/components/settings/LabeledInput";
import { LabeledSelect } from "@/components/settings/LabeledSelect";

/** Props for the contact + work authorization sub-section. */
export interface ProfileContactSectionProps {
  /** Current contact values. */
  readonly contact: SettingsProfileDto["profile"]["contact"];
  /** Current work-authorization values. */
  readonly workAuthorization: SettingsProfileDto["profile"]["work_authorization"];
  /** Country option list (U.S. pinned first). */
  readonly countryOptions: ReturnType<typeof buildPrioritizedCountryOptions>;
  /** Update a single contact field. */
  readonly onContactFieldChange: (
    fieldName: keyof SettingsProfileDto["profile"]["contact"],
    value: string,
  ) => void;
  /** Update the contact country (sets both code and label). */
  readonly onContactCountryChange: (countryCode: string) => void;
  /** Update a single work authorization field. */
  readonly onWorkAuthorizationFieldChange: (
    fieldName: keyof SettingsProfileDto["profile"]["work_authorization"],
    value: string,
  ) => void;
  /** Update the citizenship country (sets both code and label). */
  readonly onCitizenshipCountryChange: (countryCode: string) => void;
}

/**
 * Render the contact + work authorization sub-section.
 *
 * @param props - Sub-section props.
 * @returns Combined contact and work-auth markup.
 */
export function ProfileContactSection({
  contact,
  workAuthorization,
  countryOptions,
  onContactFieldChange,
  onContactCountryChange,
  onWorkAuthorizationFieldChange,
  onCitizenshipCountryChange,
}: ProfileContactSectionProps): JSX.Element {
  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
            Contact
          </h5>
          <p className="text-xs" style={{ color: COLOR_OUTLINE }}>
            Standard fields reused across job applications.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LabeledInput
            label="Full Name"
            value={contact.full_name}
            onChange={(value) => onContactFieldChange("full_name", value)}
          />
          <LabeledInput
            label="Email"
            value={contact.email}
            onChange={(value) => onContactFieldChange("email", value)}
          />
          <LabeledInput
            label="Phone"
            value={contact.phone}
            onChange={(value) => onContactFieldChange("phone", value)}
          />
          <LabeledInput
            label="City"
            value={contact.city}
            onChange={(value) => onContactFieldChange("city", value)}
          />
          <LabeledInput
            label="State / Region"
            value={contact.state_or_region}
            onChange={(value) => onContactFieldChange("state_or_region", value)}
          />
          <LabeledSelect
            label="Country"
            value={contact.country_code}
            onChange={onContactCountryChange}
            options={[
              { value: "", label: "Select country" },
              ...countryOptions.map((countryOption) => ({
                value: countryOption.code,
                label: countryOption.label,
              })),
            ]}
          />
          <LabeledInput
            label="LinkedIn URL"
            value={contact.linkedin_url}
            onChange={(value) => onContactFieldChange("linkedin_url", value)}
          />
          <LabeledInput
            label="GitHub URL"
            value={contact.github_url}
            onChange={(value) => onContactFieldChange("github_url", value)}
          />
          <LabeledInput
            label="Portfolio URL"
            value={contact.portfolio_url}
            onChange={(value) => onContactFieldChange("portfolio_url", value)}
          />
        </div>
      </div>

      <div className="space-y-4">
        <h5 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Work Authorization
        </h5>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <LabeledSelect
            label="Citizenship"
            value={workAuthorization.citizenship_country_code}
            onChange={onCitizenshipCountryChange}
            options={[
              { value: "", label: "Select citizenship country" },
              ...countryOptions.map((countryOption) => ({
                value: countryOption.code,
                label: countryOption.label,
              })),
            ]}
            helperText="United States is pinned first for faster selection."
          />
          <LabeledSelect
            label="Authorized to work in U.S.?"
            value={workAuthorization.authorized_to_work_us}
            onChange={(value) => onWorkAuthorizationFieldChange("authorized_to_work_us", value)}
            options={YES_NO_UNKNOWN_OPTIONS}
          />
          <LabeledSelect
            label="Need sponsorship now or later?"
            value={workAuthorization.requires_sponsorship_now_or_future}
            onChange={(value) =>
              onWorkAuthorizationFieldChange("requires_sponsorship_now_or_future", value)
            }
            options={YES_NO_UNKNOWN_OPTIONS}
          />
        </div>
      </div>
    </>
  );
}
