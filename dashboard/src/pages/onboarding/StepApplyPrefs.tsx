/**
 * @packageDocumentation
 *
 * Step 7 of the onboarding wizard: apply preferences and EEO defaults.
 *
 * @remarks
 * Collects eligibility, EEO demographic defaults, compensation expectations,
 * availability, location preferences, application defaults, and languages so
 * the auto-apply finisher has the data it needs without interrupting the user
 * for every form field on every job application.
 */

import type { JSX } from "react";
import { COLOR_ON_SURFACE, COLOR_ON_SURFACE_VARIANT } from "@/lib/design-tokens";
import type { ApplyPrefsDraft, LanguageEntry } from "@/lib/onboarding/types";
import { Field } from "./Field";

/** Props for {@link StepApplyPrefs}. */
export interface StepApplyPrefsProps {
  /** Current apply-preferences draft. */
  readonly draft: ApplyPrefsDraft;
  /** Replace the draft with `next`. */
  readonly onChange: (next: ApplyPrefsDraft) => void;
}

/** Proficiency options for the languages table. */
const PROFICIENCY_OPTIONS = ["basic", "conversational", "fluent", "native"] as const;

/** Section heading with optional description. */
function SectionHeader({
  title,
  description,
}: {
  readonly title: string;
  readonly description?: string;
}): JSX.Element {
  return (
    <div className="pt-2">
      <h3 className="text-sm font-bold" style={{ color: COLOR_ON_SURFACE }}>
        {title}
      </h3>
      {description && (
        <p className="text-xs mt-0.5" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {description}
        </p>
      )}
    </div>
  );
}

/**
 * Step 7: Apply preferences.
 *
 * @param props - {@link StepApplyPrefsProps}
 * @returns Apply-preferences form fields.
 */
export function StepApplyPrefs({ draft, onChange }: StepApplyPrefsProps): JSX.Element {
  /**
   * Update a top-level string field on the draft.
   *
   * @param key - Top-level field name.
   * @param value - New value.
   */
  function setTop<K extends keyof ApplyPrefsDraft>(key: K, value: ApplyPrefsDraft[K]): void {
    onChange({ ...draft, [key]: value });
  }

  /**
   * Update a nested EEO default field.
   *
   * @param key - EEO field name.
   * @param value - New value.
   */
  function setEeo(key: keyof ApplyPrefsDraft["eeo_defaults"], value: string): void {
    onChange({ ...draft, eeo_defaults: { ...draft.eeo_defaults, [key]: value } });
  }

  /**
   * Update a compensation field.
   *
   * @param key - Compensation field name.
   * @param value - Raw string from input, parsed to number or null.
   */
  function setCompensation(
    key: keyof ApplyPrefsDraft["compensation"],
    value: string,
  ): void {
    const parsed = value.trim() === "" ? null : Number(value);
    onChange({
      ...draft,
      compensation: { ...draft.compensation, [key]: parsed },
    });
  }

  /**
   * Update the availability block.
   *
   * @param key - Availability field name.
   * @param value - Raw string value from input.
   */
  function setAvailability(
    key: keyof ApplyPrefsDraft["availability"],
    value: string,
  ): void {
    const coerced: ApplyPrefsDraft["availability"][typeof key] =
      key === "notice_period_weeks"
        ? value.trim() === ""
          ? null
          : Number(value)
        : value;
    onChange({
      ...draft,
      availability: { ...draft.availability, [key]: coerced },
    });
  }

  /**
   * Update a location-preferences boolean field.
   *
   * @param key - Location preference field name.
   * @param value - New boolean value.
   */
  function setLocation(
    key: keyof ApplyPrefsDraft["location_preferences"],
    value: boolean | string[],
  ): void {
    onChange({
      ...draft,
      location_preferences: { ...draft.location_preferences, [key]: value },
    });
  }

  /**
   * Update the `preferred_cities` list from a newline-separated string.
   *
   * @param raw - Raw multiline text input.
   */
  function setPreferredCities(raw: string): void {
    const cities = raw
      .split("\n")
      .map((c) => c.trim())
      .filter(Boolean);
    setLocation("preferred_cities", cities);
  }

  /**
   * Add a blank language entry to the languages list.
   */
  function addLanguage(): void {
    const next: LanguageEntry = { language: "", proficiency: "conversational" };
    onChange({ ...draft, languages: [...draft.languages, next] });
  }

  /**
   * Update one language entry by index.
   *
   * @param index - Position in the languages array.
   * @param key - Field to update.
   * @param value - New value.
   */
  function setLanguage(
    index: number,
    key: keyof LanguageEntry,
    value: string,
  ): void {
    const updated = draft.languages.map((entry, i) =>
      i === index ? { ...entry, [key]: value } : entry,
    );
    onChange({ ...draft, languages: updated });
  }

  /**
   * Remove a language entry by index.
   *
   * @param index - Position to remove.
   */
  function removeLanguage(index: number): void {
    onChange({ ...draft, languages: draft.languages.filter((_, i) => i !== index) });
  }

  const selectClasses =
    "w-full px-3 py-2 rounded-xl border text-sm transition-colors focus:ring-2 focus:ring-primary/30";
  const checkboxClasses = "h-4 w-4 rounded border accent-primary cursor-pointer";

  const compensationMinStr =
    draft.compensation.expected_salary_min_usd === null
      ? ""
      : String(draft.compensation.expected_salary_min_usd);
  const compensationMaxStr =
    draft.compensation.expected_salary_max_usd === null
      ? ""
      : String(draft.compensation.expected_salary_max_usd);
  const compensationHourlyStr =
    draft.compensation.expected_hourly_rate_usd === null
      ? ""
      : String(draft.compensation.expected_hourly_rate_usd);
  const noticePeriodStr =
    draft.availability.notice_period_weeks === null
      ? ""
      : String(draft.availability.notice_period_weeks);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Apply Preferences
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Used by the auto-apply finisher to answer eligibility and EEO questions without
          interrupting you for every application.
        </p>
      </div>

      {/* ── Eligibility & EEO ──────────────────────────────────────── */}
      <SectionHeader
        title="Eligibility & EEO"
        description="Required fields — the finisher needs a definitive answer before it can submit applications."
      />

      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Authorized to work in the U.S.? <span style={{ color: "#b91c1c" }}>*</span>
          </span>
          <select
            className={selectClasses}
            value={draft.work_authorized_us}
            onChange={(e) => {
              setTop(
                "work_authorized_us",
                e.target.value as ApplyPrefsDraft["work_authorized_us"],
              );
            }}
          >
            <option value="unknown">— Select —</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>

        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Requires sponsorship (now or future)? <span style={{ color: "#b91c1c" }}>*</span>
          </span>
          <select
            className={selectClasses}
            value={draft.sponsorship_required_now_or_future}
            onChange={(e) => {
              setTop(
                "sponsorship_required_now_or_future",
                e.target.value as ApplyPrefsDraft["sponsorship_required_now_or_future"],
              );
            }}
          >
            <option value="unknown">— Select —</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
      </div>

      <Field
        label="Pronouns"
        value={draft.pronouns}
        onChange={(v) => {
          setTop("pronouns", v);
        }}
        placeholder="he/him, she/her, they/them, prefer not to say…"
      />

      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Gender (EEO default)
          </span>
          <Field
            label=""
            value={draft.eeo_defaults.gender}
            onChange={(v) => {
              setEeo("gender", v);
            }}
            placeholder="prefer_not_to_say"
          />
        </label>
        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Race / Ethnicity (EEO default)
          </span>
          <Field
            label=""
            value={draft.eeo_defaults.race_ethnicity}
            onChange={(v) => {
              setEeo("race_ethnicity", v);
            }}
            placeholder="prefer_not_to_say"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Veteran status (EEO default)
          </span>
          <Field
            label=""
            value={draft.eeo_defaults.veteran_status}
            onChange={(v) => {
              setEeo("veteran_status", v);
            }}
            placeholder="prefer_not_to_say"
          />
        </label>
        <label className="block">
          <span
            className="text-xs font-semibold mb-1.5 block"
            style={{ color: COLOR_ON_SURFACE_VARIANT }}
          >
            Disability status (EEO default)
          </span>
          <Field
            label=""
            value={draft.eeo_defaults.disability_status}
            onChange={(v) => {
              setEeo("disability_status", v);
            }}
            placeholder="prefer_not_to_say"
          />
        </label>
      </div>

      {/* ── Compensation & Availability ─────────────────────────────── */}
      <SectionHeader title="Compensation & Availability" />

      <div className="grid grid-cols-3 gap-4">
        <Field
          label="Min salary (USD/yr)"
          value={compensationMinStr}
          onChange={(v) => {
            setCompensation("expected_salary_min_usd", v);
          }}
          type="number"
          placeholder="e.g. 80000"
        />
        <Field
          label="Max salary (USD/yr)"
          value={compensationMaxStr}
          onChange={(v) => {
            setCompensation("expected_salary_max_usd", v);
          }}
          type="number"
          placeholder="e.g. 120000"
        />
        <Field
          label="Hourly rate (USD)"
          value={compensationHourlyStr}
          onChange={(v) => {
            setCompensation("expected_hourly_rate_usd", v);
          }}
          type="number"
          placeholder="e.g. 40"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field
          label='Earliest start date (YYYY-MM-DD or "flexible")'
          value={draft.availability.earliest_start_date}
          onChange={(v) => {
            setAvailability("earliest_start_date", v);
          }}
          placeholder="flexible"
        />
        <Field
          label="Notice period (weeks)"
          value={noticePeriodStr}
          onChange={(v) => {
            setAvailability("notice_period_weeks", v);
          }}
          type="number"
          placeholder="e.g. 2"
        />
      </div>

      {/* ── Location preferences ────────────────────────────────────── */}
      <SectionHeader title="Location preferences" />

      <div className="flex gap-6">
        <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <input
            type="checkbox"
            className={checkboxClasses}
            checked={draft.location_preferences.willing_remote}
            onChange={(e) => {
              setLocation("willing_remote", e.target.checked);
            }}
          />
          Open to remote
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <input
            type="checkbox"
            className={checkboxClasses}
            checked={draft.location_preferences.willing_hybrid}
            onChange={(e) => {
              setLocation("willing_hybrid", e.target.checked);
            }}
          />
          Open to hybrid
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          <input
            type="checkbox"
            className={checkboxClasses}
            checked={draft.location_preferences.willing_to_relocate}
            onChange={(e) => {
              setLocation("willing_to_relocate", e.target.checked);
            }}
          />
          Willing to relocate
        </label>
      </div>

      <Field
        label="Preferred cities (one per line)"
        value={draft.location_preferences.preferred_cities.join("\n")}
        onChange={setPreferredCities}
        placeholder={"New York City\nSan Francisco\nAustin"}
        multiline
      />

      {/* ── Application defaults ────────────────────────────────────── */}
      <SectionHeader
        title="Application defaults"
        description={`tier2_confidence_threshold: 1.0 means only fully-certain auto-answers are submitted; lower it to allow the finisher to attempt more fields.`}
      />

      <div className="grid grid-cols-2 gap-4">
        <Field
          label="How did you hear about us?"
          value={draft.application_defaults.how_did_you_hear}
          onChange={(v) => {
            onChange({
              ...draft,
              application_defaults: { ...draft.application_defaults, how_did_you_hear: v },
            });
          }}
          placeholder="LinkedIn, job board, referral…"
        />
        <Field
          label="Tier-2 confidence threshold (0.0–1.0)"
          value={String(draft.application_defaults.tier2_confidence_threshold)}
          onChange={(v) => {
            const parsed = v.trim() === "" ? 1.0 : Number(v);
            onChange({
              ...draft,
              application_defaults: {
                ...draft.application_defaults,
                tier2_confidence_threshold: parsed,
              },
            });
          }}
          type="number"
          placeholder="1.0"
        />
      </div>

      {/* ── Languages ───────────────────────────────────────────────── */}
      <SectionHeader
        title="Languages"
        description="Optional. Add any language you can communicate in professionally."
      />

      {draft.languages.map((entry, index) => (
        <div key={index} className="flex gap-3 items-end">
          <div className="flex-1">
            <Field
              label="Language"
              value={entry.language}
              onChange={(v) => {
                setLanguage(index, "language", v);
              }}
              placeholder="Spanish"
            />
          </div>
          <div className="w-40">
            <label className="block">
              <span
                className="text-xs font-semibold mb-1.5 block"
                style={{ color: COLOR_ON_SURFACE_VARIANT }}
              >
                Proficiency
              </span>
              <select
                className={selectClasses}
                value={entry.proficiency}
                onChange={(e) => {
                  setLanguage(index, "proficiency", e.target.value);
                }}
              >
                {PROFICIENCY_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt.charAt(0).toUpperCase() + opt.slice(1)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button
            type="button"
            className="mb-0.5 px-3 py-2.5 rounded-xl text-sm font-medium"
            style={{ color: "#b91c1c" }}
            onClick={() => {
              removeLanguage(index);
            }}
          >
            Remove
          </button>
        </div>
      ))}

      <button
        type="button"
        className="text-sm font-semibold px-4 py-2 rounded-xl border transition-colors"
        style={{ color: COLOR_ON_SURFACE_VARIANT }}
        onClick={addLanguage}
      >
        + Add language
      </button>
    </div>
  );
}
